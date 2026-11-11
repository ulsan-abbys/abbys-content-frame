"""네이버 붙여넣기를 위한 순수 마크다운 변환과 값 객체."""

from dataclasses import dataclass
from html import escape
import re


@dataclass(frozen=True)
class NaverDraft:
    title: str
    html: str
    plain: str
    has_experience_slots: bool


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
