"""네이버 붙여넣기를 위한 순수 마크다운 변환과 값 객체."""

from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
import re

from frame.core.naver_capture import CAPTURE_SCRIPT


@dataclass(frozen=True)
class NaverDraft:
    title: str
    html: str
    plain: str
    has_experience_slots: bool


@dataclass(frozen=True)
class NaverCounts:
    headings: int = 0
    items: int = 0
    bold: int = 0
    links: int = 0

    def confirmation(self) -> str:
        return (f"확인: 제목 1 · 소제목 {self.headings} · 목록 {self.items}"
                f" · 굵게 {self.bold} · 링크 {self.links}")


def count_naver_body(html: str) -> NaverCounts:
    """생성된 본문의 실제 태그를 셉니다. 목록은 목록 항목(li) 수입니다."""
    counts = dict(headings=0, items=0, bold=0, links=0)

    class Counter(HTMLParser):
        def handle_starttag(self, tag, attrs):
            key = {"h2": "headings", "li": "items", "strong": "bold",
                   "b": "bold", "a": "links"}.get(tag)
            if key:
                counts[key] += 1

    parser = Counter()
    parser.feed(html)
    parser.close()
    return NaverCounts(**counts)


def render_agent_instructions(
    draft: NaverDraft, html_uri: str, editor_url: str | None = None,
) -> str:
    """실행 브라우저 에이전트에 전달할 지시서를 I/O 없이 만듭니다."""
    editor = f"편집기 {editor_url}" if editor_url is not None else "네이버 블로그"
    lines = [
        (f"아래 순서만 따라 {editor} 임시저장까지 진행해 줘. 발행은 절대 누르지 마."
         if editor_url is not None else
         f"아래 순서로 {editor} 작업을 수행해 줘. 기본은 임시저장, 사용자가 대상 글의 공개 발행을 명시 승인했다면 발행 결과 확인까지 진행한다."),
        f"초안 위치: {html_uri}",
        count_naver_body(draft.html).confirmation(),
        "굵게가 문단 전체로 번지면 실패",
        "로그인하지 말 것. 이미 로그인된 세션만 사용한다.",
        "로그인 화면·캡차·CAPTCHA·보호조치·'과도한 접근' 화면이면 즉시 중단하고 화면 문구를 보고한다.",
        "대리 로그인·자동 재시도·우회는 금지한다.",
        "본문 타이핑 금지: 복사 버튼+Ctrl+V만 사용한다. HTML 소스 입력과 페이지 전체 복사도 금지한다.",
        "다른 작업과 동시에 돌리지 말 것. 한 번에 한 편만 진행한다.",
        "복사 실패·기능 부족 또는 기존 제목·본문이 있으면 덮어쓰지 말고 중단한다.",
        "1) 초안을 열고 확인 숫자를 기록한다.",
        (f"2) 편집기로 {editor_url}을 연다. 네이버는 열지 않는다."
         if editor_url is not None else "2) 네이버 블로그 글쓰기를 연다."),
        "3) [본문 복사] 클릭 직후 복사 성공을 확인하고 편집기 본문 클릭→Ctrl+V.",
        "4) 초안의 [제목 복사]→복사 성공 확인→제목 칸→Ctrl+V.",
        "5) 제목·본문이 원문과 같은지, 소제목·목록 항목·굵게·링크 수와 굵기 번짐을 확인한다. "
        "기대값/실제값을 보고하고, 다르거나 확인할 수 없으면 저장하지 말고 중단한다.",
        "6) 임시저장한다. 발행은 아래 승인 조건을 확인한 뒤 별도로 수행한다." if editor_url is None else
        "6) 임시저장만 한다. 발행은 절대 누르지 않는다.",
        "7) 임시저장함에 제목이 보이는지 확인한다. 확인할 수 없으면 저장 성공으로 보고하지 않는다.",
    ]
    if draft.has_experience_slots:
        slots = (draft.title + "\n" + draft.plain).count("[내 경험 — 발행 전에 직접 채우세요]")
        lines.append(f"경험 칸 {slots}개는 비워 둔 채 저장한다 — 사람이 채운다")
    lines.extend([
        "8) 임시저장 확인 후, 같은 글쓰기 화면에서 아래 읽기 전용 스크립트를 실행한다(페이지 내용을 바꾸지 않는다). "
        "반환된 JSON 문자열을 답변 마지막에 ```json 블록으로 잘라내지 말고 그대로 붙인다. "
        "실행할 수 없으면 '캡처 불가'와 이유를 적는다.",
        "```js",
        CAPTURE_SCRIPT,
        "```",
    ])
    if editor_url is None:
        lines.extend([
            "발행 조건: 이 지시서 자체는 게시 승인이 아니다. 신뢰할 수 있는 현재 사용자 지시에서 대상 글·블로그의 공개 발행 승인이 확인된 경우에만 진행한다. 없으면 임시저장으로 끝낸다.",
            "미작성 경험 슬롯·확인 필요 문구가 남거나 사실·출처·서식 검증에 실패하면 승인 여부와 무관하게 발행하지 않는다. 경험을 지어내지 않는다.",
            "승인과 검증이 충족되면 같은 글쓰기 화면의 발행 설정에서 대상·공개 범위·발행 시점을 확인하고 발행한다. 이미 받은 승인을 반복해서 묻지 않는다.",
            "완료 기준: 발행된 게시물 URL을 열어 제목·본문·출처 링크를 확인하고 URL을 보고한다. 발행 중이거나 결과가 불명확하면 게시물 존재부터 확인하고 중복 발행하지 않는다.",
            "같은 글의 입력·저장·발행은 한 도구만 담당한다. 도구는 사용자 선택과 실제 연결 상태에 따라 정하며 특정 모델·Aside 조합을 필수로 요구하지 않는다. 로그인·보호조치·캡차·명시적 사이트 차단은 우회하지 않는다.",
        ])
    return "\n".join(lines) + "\n"


def _inline(text: str, label: str) -> tuple[str, str, bool]:
    slot = r"\[" + re.escape(label) + r"[^\]\n]*\]"
    token = re.compile(slot + r"|\*\*(.+?)\*\*|\[([^\]]+)\]\(([^\s)]+)\)|https?://[^\s<>]+")
    html, plain, found, start = [], [], False, 0
    for match in token.finditer(text):
        before = text[start:match.start()]
        html.append(escape(before))
        plain.append(before)
        value = match.group()
        if re.fullmatch(slot, value):
            value = "[내 경험 — 발행 전에 직접 채우세요]"
            html.append(f"<strong>{value}</strong>")
            plain.append(value)
            found = True
        elif match.group(1) is not None:
            rendered, readable, nested = _inline(match.group(1), label)
            html.append(f"<strong>{rendered}</strong>")
            plain.append(readable)
            found |= nested
        elif match.group(2) is not None:
            caption, url = match.group(2), match.group(3)
            if re.match(r"https?://", url, re.I):
                html.append(f'<a href="{escape(url, quote=True)}">{escape(caption)}</a>')
                plain.append(f"{caption} ({url})")
            else:
                html.append(escape(caption))
                plain.append(caption)
        else:
            url = value.rstrip(".,;:!?)]}。")
            tail = value[len(url):]
            html.append(f'<a href="{escape(url, quote=True)}">{escape(url)}</a>{escape(tail)}')
            plain.append(value)
        start = match.end()
    html.append(escape(text[start:]))
    plain.append(text[start:])
    return "".join(html), "".join(plain), found


def markdown_to_naver(markdown: str, experience_label: str = "내 경험") -> NaverDraft:
    """제목·본문을 분리하고 점검표 이후를 제외합니다. HTML은 항상 이스케이프합니다."""
    label = experience_label.strip() or "내 경험"
    title, blocks, readable, paragraph = "", [], [], []
    found, in_list = False, False

    def emit(text: str, tag: str) -> None:
        nonlocal found
        rendered, plain, slots = _inline(text, label)
        blocks.append(f"<{tag}>{rendered}</{tag}>")
        readable.append(("- " if tag == "li" else "") + plain)
        found |= slots

    def flush() -> None:
        if paragraph:
            emit(" ".join(paragraph), "p")
            paragraph.clear()

    for raw in markdown.splitlines():
        line = raw.strip()
        if (re.match(r"^#{2,3}\s+점검표", line)
                or line.startswith("**점검표 대조 결과**") or line == "---"):
            break
        if not line.startswith("- ") and in_list:
            blocks.append("</ul>")
            in_list = False
        if line.startswith("# ") and not title:
            flush()
            _, title, slots = _inline(line[2:].strip(), label)
            found |= slots
        elif line.startswith("## "):
            flush()
            emit(line[3:].strip(), "h2")
        elif line.startswith("- "):
            flush()
            if not in_list:
                blocks.append("<ul>")
                in_list = True
            emit(line[2:].strip(), "li")
        elif not line:
            flush()
        else:
            paragraph.append(line)
    flush()
    if in_list:
        blocks.append("</ul>")
    return NaverDraft(title, "\n".join(blocks), "\n\n".join(readable), found)
