"""공개 페이지의 본문을 가져오는 HTTP 어댑터."""

from html import unescape
import re
from urllib.request import Request

from frame.adapters.crawl_http import USER_AGENT, can_fetch, urlopen

# 사이트가 정직한 User-Agent에 403을 반환하면 수집하지 않습니다.


def html_to_text(html: str) -> str:
    html = re.sub(r"<(script|style|nav|header|footer|aside)\b[^>]*>.*?</\1\s*>", " ", html,
                  flags=re.IGNORECASE | re.DOTALL)
    # Prefer the article body when the page marks one, so navigation text does not crowd it out.
    for tag in ("article", "main"):
        blocks = re.findall(rf"<{tag}\b[^>]*>(.*?)</{tag}\s*>", html, flags=re.IGNORECASE | re.DOTALL)
        if blocks:
            html = " ".join(blocks)
            break
    text = re.sub(r"<[^>]+>", " ", html)
    return " ".join(unescape(text).split())[:30000]


class HttpPageFetcher:
    def fetch(self, url: str) -> str | None:
        if url.lower().split("?")[0].endswith(".pdf"):
            return None
        if not can_fetch(url):
            return None
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=20) as response:
                if response.status != 200:
                    return None
                if "pdf" in (response.headers.get("Content-Type") or "").lower():
                    return None
                raw = response.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("cp949")
            return html_to_text(text)
        except Exception:
            return None
