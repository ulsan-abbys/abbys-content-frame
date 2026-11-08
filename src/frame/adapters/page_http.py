"""공개 페이지의 본문을 가져오는 HTTP 어댑터."""

from html import unescape
import re
from urllib.request import urlopen


class HttpPageFetcher:
    def fetch(self, url: str) -> str | None:
        try:
            with urlopen(url, timeout=20) as response:
                if response.status != 200:
                    return None
                raw = response.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("cp949")
            text = re.sub(r"<(script|style)\b[^>]*>.*?</\1\s*>", " ", text,
                          flags=re.IGNORECASE | re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            return " ".join(unescape(text).split())[:30000]
        except Exception:
            return None
