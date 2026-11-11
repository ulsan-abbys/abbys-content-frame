"""네트워크 없이 URL과 robots.txt 응답을 판정하는 순수 정책."""

import re
from urllib.parse import quote, unquote, urlsplit
from urllib.robotparser import RobotFileParser

UA_TOKEN = "abbys-content-frame"
BLOCKED_HOSTS = frozenset({
    "blog.naver.com", "m.blog.naver.com", "cafe.naver.com",
    "m.cafe.naver.com", "post.naver.com", "kin.naver.com",
})


def _normalize(value: str) -> str:
    """비예약 ASCII만 디코딩하고 나머지 옥텟의 표기를 정규화합니다."""
    def percent(match):
        char = chr(int(match[1], 16))
        return char if re.fullmatch(r"[A-Za-z0-9._~-]", char) else match[0].upper()
    return re.sub(r"%([0-9a-fA-F]{2})", percent,
                  quote(value, safe="/!$&'()*+,;=:@?%-._~"))


class RobotsPolicy(RobotFileParser):
    """표준 파서에 RFC 9309 그룹 병합·최장 일치·특수문자를 보완합니다."""

    def modified(self):
        # 순수 파싱 중 시계를 읽지 않습니다. 유효기간은 HTTP 경계가 관리합니다.
        self.last_checked = 1

    def _add_entry(self, entry):
        self.entries.append(entry)

    def can_fetch(self, useragent, url):
        if self.disallow_all or not (self.last_checked or self.allow_all):
            return False
        if self.allow_all:
            return True
        token = useragent.split("/")[0].lower()
        groups = [e for e in self.entries if token in [a.lower() for a in e.useragents]]
        if not groups:
            groups = [e for e in self.entries if "*" in e.useragents]
        parts = urlsplit(url)
        target = _normalize((parts.path or "/") + ("?" + parts.query if parts.query else ""))
        matches = []
        for entry in groups:
            for rule in entry.rulelines:
                path = _normalize(unquote(rule.path))
                if not path:
                    continue
                anchored = path.endswith("$")
                pattern = path[:-1] if anchored else path
                regex = "^" + ".*".join(re.escape(p) for p in pattern.split("*"))
                if re.search(regex + ("$" if anchored else ""), target):
                    length = len(re.sub(r"%[0-9A-F]{2}", "x", pattern.replace("*", "")))
                    matches.append((length, rule.allowance))
        return max(matches)[1] if matches else True


def origin(url: str) -> str | None:
    """차단 호스트와 비 HTTP 주소는 요청 전에 거부합니다."""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
        if (parts.scheme not in ("http", "https") or not host
                or host in BLOCKED_HOSTS or parts.username is not None
                or parts.password is not None):
            return None
        port = parts.port or (443 if parts.scheme == "https" else 80)
        host = f"[{host}]" if ":" in host else host
        return f"{parts.scheme}://{host}:{port}"
    except ValueError:
        return None


def parse_robots(status: int, body: str = "") -> RobotFileParser:
    """4xx는 허용, 5xx와 그 밖의 불확실한 응답은 차단합니다."""
    parser = RobotsPolicy()
    if 200 <= status < 300:
        # 파서의 사전 unquote가 예약 문자를 손실하지 않도록 보호합니다.
        parser.parse([line.replace("%", "%25") for line in body.lstrip("\ufeff").splitlines()
                      if line.strip()])
    elif 400 <= status < 500:
        parser.allow_all = True
    else:
        parser.disallow_all = True
    return parser
