"""다른 출처 검증 서비스는 UrlChecker.check를 구현해 교체하세요."""

from urllib.error import URLError
from urllib.request import Request

from frame.adapters.crawl_http import USER_AGENT, can_fetch, urlopen


class HttpUrlChecker:
    def check(self, url: str, keywords: list[str]) -> bool:
        if not can_fetch(url):
            return False
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=20) as response:
                if response.status != 200:
                    return False
                data = response.read()
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("cp949")
            return all(keyword in text for keyword in keywords)
        except (URLError, OSError, UnicodeError, ValueError):
            return False
