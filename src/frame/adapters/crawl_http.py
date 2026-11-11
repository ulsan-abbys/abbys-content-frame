"""정직한 식별자, robots 캐시, 리다이렉트 검사를 공유하는 HTTP 경계."""

from http.client import HTTPException
from importlib.metadata import PackageNotFoundError, version
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from frame.adapters.crawl_policy import UA_TOKEN, origin, parse_robots

try:
    PACKAGE_VERSION = version("abbys-content-frame")
except PackageNotFoundError:
    PACKAGE_VERSION = "0.x"
USER_AGENT = f"{UA_TOKEN}/{PACKAGE_VERSION} (+https://github.com/ulsan-abbys/abbys-content-frame)"
CACHE_SECONDS = 24 * 60 * 60
_robots_cache = {}


class PolicyRedirect(HTTPRedirectHandler):
    def __init__(self, robots=False):
        self.robots = robots

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # robots 자체의 리다이렉트는 재귀 검사하지 않지만 금지 호스트는 차단합니다.
        if origin(newurl) is None or (not self.robots and not can_fetch(newurl)):
            raise URLError("수집 정책이 리다이렉트 대상을 차단했습니다.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_robots(request, timeout):
    return build_opener(PolicyRedirect(robots=True)).open(request, timeout=timeout)


def can_fetch(url: str) -> bool:
    site = origin(url)
    if site is None:
        return False
    now = monotonic()
    cached = _robots_cache.get(site)
    if cached is None or now - cached[0] >= CACHE_SECONDS:
        try:
            request = Request(site + "/robots.txt", headers={"User-Agent": USER_AGENT})
            with _open_robots(request, timeout=20) as response:
                parser = parse_robots(response.status, response.read().decode("utf-8", errors="replace"))
        except HTTPError as exc:
            parser = parse_robots(exc.code)
            exc.close()
        except (OSError, ValueError, HTTPException):
            parser = parse_robots(503)
        _robots_cache[site] = (now, parser)
    else:
        parser = cached[1]
    return parser.can_fetch(UA_TOKEN, url)


def urlopen(request, timeout=20):
    """호출자는 최초 URL을 검사하고 이 경계는 이동 대상도 검사합니다."""
    return build_opener(PolicyRedirect()).open(request, timeout=timeout)
