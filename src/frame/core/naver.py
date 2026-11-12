"""네이버 붙여넣기를 위한 순수 마크다운 변환과 값 객체."""

from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
import re


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


def render_agent_instructions(draft: NaverDraft, html_uri: str) -> str:
    """실행 브라우저 에이전트에 전달할 지시서를 I/O 없이 만듭니다."""
    lines = [
        "아래 순서만 따라 네이버 블로그 임시저장까지 진행해 줘. 발행은 절대 누르지 마.",
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
        "2) 네이버 블로그 글쓰기를 연다.",
        "3) [본문 복사] 클릭 직후 복사 성공을 확인하고 편집기 본문 클릭→Ctrl+V.",
        "4) 초안의 [제목 복사]→복사 성공 확인→제목 칸→Ctrl+V.",
        "5) 제목·본문이 원문과 같은지, 소제목·목록 항목·굵게·링크 수와 굵기 번짐을 확인한다. "
        "기대값/실제값을 보고하고, 다르거나 확인할 수 없으면 저장하지 말고 중단한다.",
        "6) 임시저장만 한다. 발행은 절대 누르지 않는다.",
        "7) 임시저장함에 제목이 보이는지 확인한다. 확인할 수 없으면 저장 성공으로 보고하지 않는다.",
    ]
    if draft.has_experience_slots:
        slots = (draft.title + "\n" + draft.plain).count("[내 경험 — 발행 전에 직접 채우세요]")
        lines.append(f"경험 칸 {slots}개는 비워 둔 채 저장한다 — 사람이 채운다")
    lines.append(
        "끝나면 사람이 개발자도구 Console에 `frame naver capture-script` 출력(사람이 붙여 줌)을 "
        "실행해 결과 JSON을 확인 담당 사람에게 전달한다. 이 단계는 에이전트가 아니라 사람이 수행한다."
    )
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
