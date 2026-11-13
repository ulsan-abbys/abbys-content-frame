"""처음 쓰는 사람을 위한 주제 설정 저장과 준비 상태 점검."""

import json
import os
from http.client import HTTPException
from pathlib import Path
import tomllib
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from frame.adapters.engines import EngineUnavailable, select_engine
from frame.core.ports import NaverTransport

GUIDE = "docs/API_키_발급_가이드.md"
NAVER_URL = "https://openapi.naver.com/v1/datalab/search"


def validate_topics(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("주제 설정은 JSON 객체여야 합니다.")
    result = {}
    for key, label in (("field", "분야"), ("region", "지역"), ("audience", "독자")):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label}을 입력하세요.")
        result[key] = value.strip()
    for key, label in (("seed_keywords", "씨앗 검색어"), ("exclude", "제외할 주제"),
                       ("issue_sources", "이슈 출처 URL")):
        value = data.get(key, [] if key != "seed_keywords" else None)
        if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
            raise ValueError(f"{label}은 비어 있지 않은 문자열의 목록으로 입력하세요.")
        result[key] = [v.strip() for v in value]
    if not 3 <= len(result["seed_keywords"]) <= 10:
        raise ValueError("씨앗 검색어는 3~10개 입력하세요.")
    for value in result["issue_sources"]:
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or any(c.isspace() for c in value):
            raise ValueError("이슈 출처는 http:// 또는 https://로 시작하는 URL을 입력하세요.")
    cadence = data.get("cadence_per_week")
    if type(cadence) is not int or cadence < 1:
        raise ValueError("주당 글 수는 1 이상의 정수로 입력하세요.")
    result["cadence_per_week"] = cadence
    return result


def ask_topics() -> dict:
    print("내 블로그가 다룰 내용을 정합니다. 목록은 쉼표로 구분하세요.")
    data = {}
    for key, prompt in (("field", "어떤 분야를 쓰나요? "), ("region", "어느 지역을 다루나요? "),
                        ("audience", "누가 읽으면 좋을까요? "),
                        ("seed_keywords", "씨앗 검색어 3~10개는 무엇인가요? "),
                        ("exclude", "제외할 주제는 무엇인가요? (없으면 Enter) "),
                        ("issue_sources", "공식 사이트에서 복사한 RSS URL은 무엇인가요? (없으면 Enter) "),
                        ("cadence_per_week", "일주일에 글을 몇 편 쓰나요? ")):
        while True:
            value = input(prompt).strip()
            if key in ("seed_keywords", "exclude", "issue_sources"):
                value = [part.strip() for part in value.split(",") if part.strip()]
            elif key == "cadence_per_week":
                try:
                    value = int(value)
                except ValueError:
                    print("1 이상의 정수를 입력하세요.")
                    continue
            trial = dict(field="분야", region="지역", audience="독자",
                         seed_keywords=["가", "나", "다"], cadence_per_week=1)
            trial[key] = value
            try:
                validate_topics(trial)
            except ValueError as exc:
                print(exc)
                continue
            data[key] = value
            break
    return validate_topics(data)


def save_topics(path: Path, data: object, *, template: Path | None = None) -> None:
    topics = validate_topics(data)
    source = path if path.exists() else template
    original = source.read_text(encoding="utf-8-sig") if source is not None and source.exists() else ""
    before = tomllib.loads(original)
    lines = original.splitlines(keepends=True)
    headers = []
    for index, line in enumerate(lines):
        if not line.lstrip().startswith("["):
            continue
        try:
            # 여러 줄 문자열과 배열 내부의 가짜 표 제목은 건너뜁니다.
            tomllib.loads("".join(lines[:index]))
            header = tomllib.loads(line)
        except tomllib.TOMLDecodeError:
            continue
        headers.append((index, header))
    spans = []
    for pos, (start, header) in enumerate(headers):
        if "topics" in header:
            end = headers[pos + 1][0] if pos + 1 < len(headers) else len(lines)
            spans.append((start, end))
    for start, end in reversed(spans):
        del lines[start:end]
    section = "[topics]\n" + "".join(
        f"{key} = {json.dumps(value, ensure_ascii=False)}\n" for key, value in topics.items())
    updated = "".join(lines).rstrip("\n") + "\n\n" + section
    try:
        after = tomllib.loads(updated)
    except tomllib.TOMLDecodeError:
        raise ValueError("주제 표를 바꿀 수 없습니다. 프로필의 topics를 [topics] 표로 정리하세요.") from None
    if {k: v for k, v in before.items() if k != "topics"} != {k: v for k, v in after.items() if k != "topics"}:
        raise ValueError("다른 설정을 보존할 수 없어 저장하지 않았습니다.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated.lstrip("\n") if not original else updated, encoding="utf-8", newline="\n")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpNaverTransport:
    def post(self, url: str, headers: dict[str, str], body: bytes) -> int:
        request = Request(url, data=body, headers=headers, method="POST")
        try:
            # 인증 헤더를 다른 주소로 전달하거나 요청을 재시도하지 않습니다.
            with build_opener(NoRedirect()).open(request, timeout=10) as response:
                return response.status
        except HTTPError as exc:
            code = exc.code
            exc.close()
            return code


def doctor(path: Path, *, check_naver: bool = False,
           transport: NaverTransport | None = None) -> int:
    print("항목 | 상태 | 다음 할 일 | 안내 문서")

    def row(label, status, step="없음"):
        print(f"{label} | {status} | {step} | {GUIDE}")

    for engine in ("claude", "codex"):
        try:
            select_engine(engine)
            row(f"{engine} CLI", "있음 (PATH, 로그인은 직접 확인)")
        except EngineUnavailable:
            row(f"{engine} CLI", "없음 (둘 중 하나만 필요)", "사용할 CLI라면 설치 후 로그인하세요")
    try:
        row("선택 엔진", select_engine())
    except EngineUnavailable:
        row("선택 엔진", "없음", "CLI 설치 후 FRAME_ENGINE을 auto, claude 또는 codex로 설정하세요")
    try:
        validate_topics(tomllib.loads(path.read_text(encoding="utf-8-sig")).get("topics"))
        row("프로필 [topics]", "준비됨")
    except (OSError, ValueError):
        row("프로필 [topics]", "미완료", f'frame setup topics --profile "{path}"를 실행하세요')
    for name in ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "DATA_GO_KR_SERVICE_KEY"):
        optional = name == "DATA_GO_KR_SERVICE_KEY"
        row(name + (" (선택)" if optional else ""), "있음" if os.environ.get(name) else "없음",
            "없음" if os.environ.get(name) else
            ("기상특보가 필요하면 서비스키를 발급받아 환경 변수에 저장하세요" if optional else
             "네이버 내 애플리케이션에서 발급값을 환경 변수에 저장하세요"))
    if check_naver:
        if not all(os.environ.get(key) for key in ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET")):
            row("네이버 연결", "건너뜀", "NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 먼저 설정하세요")
        else:
            body = json.dumps({"startDate": "2024-01-01", "endDate": "2024-01-02", "timeUnit": "date",
                               "keywordGroups": [{"groupName": "생활", "keywords": ["생활"]}]}).encode("utf-8")
            headers = {"X-Naver-Client-Id": os.environ["NAVER_CLIENT_ID"],
                       "X-Naver-Client-Secret": os.environ["NAVER_CLIENT_SECRET"],
                       "Content-Type": "application/json", "User-Agent": "abbys-content-frame/setup-doctor"}
            try:
                status = (transport if transport is not None else HttpNaverTransport()).post(NAVER_URL, headers, body)
                row("네이버 연결", "OK" if status == 200 else f"HTTP {status}",
                    "없음" if status == 200 else "내 애플리케이션의 키·API 권한·호출 한도를 확인하세요")
            except (OSError, ValueError, HTTPException):
                row("네이버 연결", "연결 실패", "인터넷 연결을 확인하세요")
    return 0
