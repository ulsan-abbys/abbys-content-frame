"""브라우저 실패 때도 직접 열 수 있는 HTML 사본을 저장합니다."""

from html import escape
from pathlib import Path

from frame.core.naver import NaverDraft, count_naver_body, render_agent_instructions


_COPY_UI = """
<style>
#frame-bar { position:sticky; top:0; z-index:1; background:#fff8e6;
 border-bottom:2px solid #f0b400; padding:12px 16px; font:15px sans-serif; }
#frame-bar button { margin:8px 8px 8px 0; padding:8px 14px; font-size:15px; }
#frame-body { max-width:800px; margin:24px auto; padding:0 16px; line-height:1.7; }
</style>
<div id="frame-bar">
<div>붙여넣기 순서: 1. [본문 복사] → 2. 편집기 본문 클릭 → Ctrl+V →
3. [제목 복사] → 제목 칸 클릭 → Ctrl+V → 4. 서식 확인 → 임시저장 (명시 승인한 글은 에이전트 발행 가능)</div>
<button id="copy-body" type="button">본문 복사</button>
<button id="copy-title" type="button">제목 복사</button>
<span id="copy-status" role="status" aria-live="polite"></span>
"""

_COPY_SCRIPT = """
<script>
const bodyEl = document.getElementById('frame-body');
const statusEl = document.getElementById('copy-status');
async function copyContent(target, label) {
  try {
    await navigator.clipboard.write([new ClipboardItem({
      'text/html': new Blob([target.innerHTML], {type: 'text/html'}),
      'text/plain': new Blob([target.innerText], {type: 'text/plain'})
    })]);
    statusEl.textContent = label + ' 복사됨 — 붙여넣을 칸을 클릭하고 Ctrl+V';
  } catch (error) {
    const selection = window.getSelection();
    const range = document.createRange();
    const previous = [];
    for (let i = 0; i < selection.rangeCount; i++) {
      previous.push(selection.getRangeAt(i).cloneRange());
    }
    try {
      range.selectNodeContents(target);
      selection.removeAllRanges();
      selection.addRange(range);
      if (!document.execCommand('copy')) throw new Error('복사 실패');
      statusEl.textContent = label + ' 복사됨(대체 방식) — 붙여넣은 서식을 확인하세요';
    } catch (fallbackError) {
      statusEl.textContent = label + ' 복사 실패 — 중단하고 사람이 직접 복사하세요';
    } finally {
      selection.removeAllRanges();
      for (const saved of previous) selection.addRange(saved);
    }
  }
}
document.getElementById('copy-body').addEventListener('click', () => copyContent(bodyEl, '본문'));
document.getElementById('copy-title').addEventListener('click', async () => {
  const titleEl = document.createElement('div');
  titleEl.textContent = document.title;
  titleEl.style.position = 'fixed';
  titleEl.style.left = '-10000px';
  document.body.appendChild(titleEl);
  try { await copyContent(titleEl, '제목'); }
  finally { titleEl.remove(); }
});
</script>
"""


def save_naver_html(source: Path, draft: NaverDraft) -> Path:
    destination = source.with_suffix(".naver.html")
    destination.write_text(
        '<!doctype html>\n<html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(draft.title)}</title></head><body>\n'
        f'{_COPY_UI}<div id="frame-confirmation">'
        f'{count_naver_body(draft.html).confirmation()}</div></div>\n'
        f'<div id="frame-body">{draft.html}</div>\n{_COPY_SCRIPT}</body></html>\n',
        encoding="utf-8",
        newline="\n",
    )
    return destination


def save_agent_instructions(
    source: Path, draft: NaverDraft, html_path: Path, editor_url: str | None = None,
) -> Path:
    """HTML의 절대 URI를 담은 실행 지시서를 UTF-8·LF로 저장합니다."""
    destination = source.with_suffix(".agent.txt")
    destination.write_text(
        render_agent_instructions(draft, html_path.resolve().as_uri(), editor_url),
        encoding="utf-8", newline="\n",
    )
    return destination
