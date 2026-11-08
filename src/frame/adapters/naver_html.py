"""브라우저 실패 때도 직접 열 수 있는 HTML 사본을 저장합니다."""

from html import escape
from pathlib import Path

from frame.core.naver import NaverDraft


def save_naver_html(source: Path, draft: NaverDraft) -> Path:
    destination = source.with_suffix(".naver.html")
    destination.write_text(
        '<!doctype html>\n<html lang="ko"><head><meta charset="utf-8">'
        f'<title>{escape(draft.title)}</title></head><body>\n'
        f'<h1>{escape(draft.title)}</h1>\n{draft.html}\n</body></html>\n',
        encoding="utf-8",
    )
    return destination
