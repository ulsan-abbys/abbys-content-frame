"""변환 HTML과 읽기 전용 캡처를 대조하는 순수 판정."""

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from html.parser import HTMLParser
import math
import re
from statistics import median
import unicodedata

from frame.core.naver import markdown_to_naver


def normalize(text: str) -> str:
    text = re.sub(r"[\u200b-\u200d\u2060\ufeff]", "", text)
    return " ".join(unicodedata.normalize("NFC", text).split())


def compact(text: str) -> str:
    return "".join(normalize(text).split())


@dataclass
class Expected:
    title: str
    headings: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    bolds: list[str] = field(default_factory=list)
    full_bold_blocks: list[str] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    body: list[str] = field(default_factory=list)
    slot_count: int = 0
    slot_text: str = "[내 경험 — 발행 전에 직접 채우세요]"


def extract_expected(markdown: str, experience_label: str = "내 경험") -> Expected:
    draft = markdown_to_naver(markdown, experience_label)
    result = Expected(title=draft.title)

    class Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []

        def handle_starttag(self, tag, attrs):
            self.stack.append((tag, dict(attrs), [], []))

        def handle_data(self, data):
            bold = any(tag in ("strong", "b") for tag, _, _, _ in self.stack)
            for _, _, parts, plain_parts in self.stack:
                parts.append(data)
                if not bold:
                    plain_parts.append(data)

        def handle_endtag(self, tag):
            current, attrs, parts, plain_parts = self.stack.pop()
            text = normalize("".join(parts))
            if current in ("p", "h2", "li"):
                result.body.append(text)
                if text and not normalize("".join(plain_parts)):
                    result.full_bold_blocks.append(text)
            target = {"p": result.paragraphs, "h2": result.headings,
                      "li": result.items, "strong": result.bolds, "b": result.bolds}.get(current)
            if target is not None:
                target.append(text)
            if current == "a":
                result.links.append((text, attrs.get("href", "")))

    parser = Parser()
    parser.feed(draft.html)
    parser.close()
    result.slot_count = (draft.title + " ".join(result.body)).count(result.slot_text)
    if not normalize(result.title) or not result.body:
        raise ValueError("초안에 '# 제목'과 비어 있지 않은 본문이 필요합니다.")
    return result


def _decode_query(value: str) -> str:
    # URL의 쿼리만 디코드합니다. 네트워크 모듈에 의존하지 않습니다.
    value = value.replace("+", " ")
    return re.sub(r"(?:%[0-9a-fA-F]{2})+",
                  lambda m: bytes.fromhex(m.group().replace("%", "")).decode("utf-8", "replace"), value)


def normalize_href(href: str) -> str:
    href = normalize(href)
    for _ in range(5):
        match = re.match(r"^([a-zA-Z][\w+.-]*)://([^/?#]+)(.*)$", href)
        if not match:
            return href.rstrip("/")
        scheme, authority, rest = match.groups()
        host = authority.lower().split(":", 1)[0]
        if host == "naver.com" or host.endswith(".naver.com"):
            query = rest.partition("?")[2].partition("#")[0]
            params = dict(part.partition("=")[::2] for part in query.split("&") if "=" in part)
            target = params.get("url") or params.get("u")
            if target:
                href = _decode_query(target)
                continue
        return f"{scheme.lower()}://{authority.lower()}{rest}".rstrip("/")
    return href.rstrip("/")


def validate_capture(capture: dict) -> None:
    if not isinstance(capture, dict) or not isinstance(capture.get("title"), str):
        raise ValueError("캡처에는 문자열 제목이 필요합니다.")
    for key in ("blocks", "bolds", "links"):
        if not isinstance(capture.get(key), list):
            raise ValueError(f"캡처의 {key}는 목록이어야 합니다.")
    for block in capture["blocks"]:
        if not isinstance(block, dict):
            raise ValueError("캡처 블록은 객체여야 합니다.")
        for key in ("text", "tag", "cls"):
            if not isinstance(block.get(key), str):
                raise ValueError(f"블록의 {key}는 문자열이어야 합니다.")
        for key in ("fontSize", "fontWeight"):
            value = block.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"블록의 {key}는 유한한 양수 또는 0이어야 합니다.")
        for key in ("inList", "bulletPrefix"):
            if not isinstance(block.get(key), bool):
                raise ValueError(f"블록의 {key}는 참/거짓이어야 합니다.")
    if any(not isinstance(value, str) for value in capture["bolds"]):
        raise ValueError("굵게 목록은 문자열이어야 합니다.")
    for link in capture["links"]:
        if not isinstance(link, dict) or any(not isinstance(link.get(k), str) for k in ("text", "href")):
            raise ValueError("링크에는 문자열 text와 href가 필요합니다.")


def check_naver(markdown: str, capture: dict, experience_label: str = "내 경험",
                stage: str = "draft") -> dict:
    if stage not in ("draft", "publish"):
        raise ValueError("단계는 draft 또는 publish여야 합니다.")
    validate_capture(capture)
    expected = extract_expected(markdown, experience_label)
    items = []

    def add(code, status, message):
        items.append(dict(code=code, status=status, message=message))

    blocks = capture["blocks"]
    texts = [normalize(b["text"]) for b in blocks]
    clean = [re.sub(r"^(?:[•·*\-]|\d+[.)])\s*", "", t) if b["bulletPrefix"] else t
             for b, t in zip(blocks, texts)]
    body_sizes = [b["fontSize"] for b, t in zip(blocks, texts)
                  if t not in expected.headings and b["fontSize"] > 0]
    baseline = median(body_sizes) if body_sizes else 0
    add("C1", "PASS" if normalize(capture["title"]) == normalize(expected.title) else "FAIL", "제목 대조")
    used = set()
    positions = []
    for heading in expected.headings:
        index = next((i for i, t in enumerate(texts) if t == heading and i not in used), None)
        if index is None:
            add("C2", "FAIL", f"소제목 없음: {heading}")
            continue
        used.add(index)
        positions.append(index)
        b = blocks[index]
        structural = (b["tag"].lower() in ("h1", "h2", "h3", "h4")
                      or re.search(r"title|heading|sectionTitle|quotation", b["cls"], re.I)
                      or (baseline > 0 and b["fontSize"] >= baseline * 1.15))
        status = "PASS" if structural else "WARN" if b["fontWeight"] >= 600 else "FAIL"
        message = {"PASS": "소제목 유지", "WARN": "굵은 문단으로 바뀜", "FAIL": "일반 문단으로 녹음"}[status]
        add("C2", status, f"{message}: {heading}")
    add("C2_ORDER", "PASS" if len(positions) == len(expected.headings) and positions == sorted(positions) else "FAIL",
        "소제목 순서 대조")
    used = set()
    for item in expected.items:
        candidates = [i for i, t in enumerate(clean) if t == item and i not in used]
        index = next((i for i in candidates if blocks[i]["inList"] or blocks[i]["bulletPrefix"]),
                     candidates[0] if candidates else None)
        good = index is not None and (blocks[index]["inList"] or blocks[index]["bulletPrefix"])
        if index is not None:
            used.add(index)
        add("C3", "PASS" if good else "FAIL", f"{'목록 유지' if good else '글머리 사라짐' if index is not None else '목록 없음'}: {item}")
    for bold in expected.bolds:
        good = any(bold in normalize(value) for value in capture["bolds"])
        add("C4", "PASS" if good else "FAIL", f"굵게 {'유지' if good else '없음'}: {bold}")
    allowed_bold = set(expected.headings + expected.full_bold_blocks)
    body_blocks = [(b, t) for b, t in zip(blocks, clean)
                   if t and t not in allowed_bold
                   and (b["tag"].lower() in ("p", "li")
                        or "se-text-paragraph" in b["cls"].split()
                        or b["inList"] or b["bulletPrefix"])]
    captured_bolds = [normalize(value) for value in capture["bolds"]]
    excessive = [t for b, t in body_blocks
                 if b["fontWeight"] >= 600
                 or any(t in bold or (bold in t and len(bold) >= len(t) * .9)
                        for bold in captured_bolds)]
    n, m = len(excessive), len(body_blocks)
    if n == 0:
        add("C4B", "PASS", "과다 굵게 없음")
    elif n / m <= .2:
        add("C4B", "WARN", f"원고에 없는 굵은 문단 {n}개 · "
            + " / ".join(text[:30] for text in excessive[:3]))
    else:
        add("C4B", "FAIL", f"굵기 번짐: 본문 {m}개 중 {n}개가 굵게")
    for text, href in expected.links:
        matches = [link for link in capture["links"] if normalize_href(link["href"]) == normalize_href(href)]
        status = "PASS" if any(normalize(link["text"]) == text for link in matches) else "WARN" if matches else "FAIL"
        add("C5", status, f"{'링크 유지' if status == 'PASS' else '링크 텍스트 다름' if matches else '링크 없음'}: {text}")
    actual = compact(" ".join(clean))
    ratio = SequenceMatcher(None, compact(" ".join(expected.body)), actual, autojunk=False).ratio()
    missing = [p for p in expected.paragraphs if compact(p) not in actual][:5]
    add("C6", "PASS" if ratio >= .97 else "WARN" if ratio >= .90 else "FAIL",
        f"본문 보존 {ratio:.1%}" + (" · 빠진 문단: " + " / ".join(missing) if missing else ""))
    all_text = normalize(capture["title"] + " " + " ".join(texts))
    leaks = [token for token in ("본문 복사", "제목 복사", "붙여넣기 순서", "확인: 제목", "**", "## ", "](http") if token in all_text]
    add("C7", "FAIL" if leaks else "PASS", "안내·마크다운 누출: " + ", ".join(leaks) if leaks else "누출 없음")
    slots = all_text.count(expected.slot_text)
    add("C8", ("FAIL" if stage == "publish" else "WARN") if slots else "PASS",
        f"발행 전 채울 칸 {slots}개" if slots else "경험 칸 없음")
    if slots < expected.slot_count:
        add("C8_INFO", "PASS", "정보: 경험 칸이 기대보다 적습니다. 실제 작성 여부는 사람이 확인하세요.")
    counts = {name: {"matched": sum(i["code"] == code and i["status"] == "PASS" for i in items), "total": total}
              for name, code, total in (("headings", "C2", len(expected.headings)), ("items", "C3", len(expected.items)),
                                        ("bolds", "C4", len(expected.bolds)), ("links", "C5", len(expected.links)))}
    verdict = "FAIL" if any(i["status"] == "FAIL" for i in items) else "WARN" if any(i["status"] == "WARN" for i in items) else "PASS"
    return dict(items=items, verdict=verdict, counts=counts)
