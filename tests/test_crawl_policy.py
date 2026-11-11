"""수집 정책은 실제 네트워크 없이 검사합니다."""

from contextlib import nullcontext
from http.client import IncompleteRead
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from frame.adapters import crawl_http, page_http, url_http
from frame.adapters.crawl_policy import BLOCKED_HOSTS, UA_TOKEN, origin, parse_robots


@pytest.fixture(autouse=True)
def isolated_network(monkeypatch):
    crawl_http._robots_cache.clear()
    def unexpected(*args, **kwargs):
        pytest.fail("예상하지 않은 네트워크 요청")
    monkeypatch.setattr(crawl_http, "_open_robots", unexpected)
    monkeypatch.setattr(page_http, "urlopen", unexpected)
    monkeypatch.setattr(url_http, "urlopen", unexpected)
    yield
    crawl_http._robots_cache.clear()


def response(status=200, body=b""):
    return nullcontext(SimpleNamespace(status=status, headers={}, read=lambda: body))


@pytest.mark.parametrize("host", sorted(BLOCKED_HOSTS))
@pytest.mark.parametrize("suffix", ["", ":8443", "."])
def test_blocked_without_network(host, suffix):
    url = f"https://{host.upper()}{suffix}/post"
    assert origin(url) is None
    assert page_http.HttpPageFetcher().fetch(url) is None
    assert url_http.HttpUrlChecker().check(url, []) is False


@pytest.mark.parametrize("url", ["file:///x", "https://", "http://host:bad/", "https://user@host/", "http://[bad"])
def test_invalid_without_network(url):
    assert not crawl_http.can_fetch(url)


@pytest.mark.parametrize("status,allowed", [(200, True), (204, True), (400, True), (401, True), (403, True), (404, True), (429, True), (500, False), (503, False), (302, False)])
def test_status_policy(status, allowed):
    assert parse_robots(status).can_fetch(UA_TOKEN, "https://example.com/x") is allowed


@pytest.mark.parametrize("rules,path,allowed", [
    ("User-agent: *\nDisallow: /private", "/private/x", False),
    ("User-agent: *\nDisallow: /", "/", False),
    ("User-agent: *\nDisallow:", "/x", True),
    ("User-agent: *\nDisallow: /\nAllow: /public", "/public/x", True),
    ("User-agent: *\nDisallow: /x\nAllow: /x", "/x", True),
    ("User-agent: *\nDisallow: /*.pdf$", "/x.pdf", False),
    ("User-agent: *\nDisallow: /*.pdf$", "/x.pdf?a=1", True),
    ("User-agent: *\nDisallow: /x?secret=", "/x?secret=1", False),
    ("User-agent: *\nDisallow: /한글", "/%ED%95%9C%EA%B8%80", False),
    ("User-agent: *\nDisallow: /%7Euser", "/~user", False),
    ("User-agent: *\nDisallow: /a%2Fb", "/a/b", True),
    ("User-agent: *\nDisallow: /a%2Fb", "/a%2fb", False),
    ("User-agent: *\nDisallow: /a%2Ab", "/axyzb", True),
    ("User-agent: *\nDisallow: /\n\nUser-agent: ABBYS-CONTENT-FRAME\nAllow: /", "/x", True),
    ("User-agent: abbys-content-frame\nDisallow: /a\n\nUser-agent: abbys-content-frame\nDisallow: /b", "/b", False),
    ("User-agent: *\nDisallow: /a\n\nUser-agent: *\nDisallow: /b", "/b", False),
])
def test_robots_rules(rules, path, allowed):
    assert parse_robots(200, rules).can_fetch(UA_TOKEN, "https://example.com" + path) is allowed


@pytest.mark.parametrize("status,allowed", [(403, True), (404, True), (500, False)])
def test_http_errors(monkeypatch, status, allowed):
    def fail(*args, **kwargs):
        raise HTTPError("https://example.com/robots.txt", status, "test", {}, None)
    monkeypatch.setattr(crawl_http, "_open_robots", fail)
    assert crawl_http.can_fetch("https://example.com/x") is allowed


@pytest.mark.parametrize("error", [URLError("offline"), TimeoutError(), OSError(), IncompleteRead(b"")])
def test_robots_network_failure_blocks_content(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(crawl_http, "_open_robots", fail)
    assert page_http.HttpPageFetcher().fetch("https://example.com/x") is None
    assert not url_http.HttpUrlChecker().check("https://example.com/x", [])


def test_robots_disallow_blocks_both_fetchers(monkeypatch):
    monkeypatch.setattr(crawl_http, "_open_robots", lambda *a, **k: response(200, b"User-agent: *\nDisallow: /"))
    assert page_http.HttpPageFetcher().fetch("https://example.com/x") is None
    assert not url_http.HttpUrlChecker().check("https://example.com/x", [])


def test_cache_origin_and_expiry(monkeypatch):
    now = [100.0]
    calls = []
    monkeypatch.setattr(crawl_http, "monotonic", lambda: now[0])
    def robots(req, timeout):
        calls.append(req.full_url)
        assert req.get_header("User-agent") == crawl_http.USER_AGENT
        return response(404)
    monkeypatch.setattr(crawl_http, "_open_robots", robots)
    assert crawl_http.can_fetch("https://example.com/a")
    assert crawl_http.can_fetch("https://EXAMPLE.COM:443/b")
    now[0] += 86399
    assert crawl_http.can_fetch("https://example.com/c")
    assert len(calls) == 1
    now[0] += 1
    assert crawl_http.can_fetch("https://example.com/c")
    assert len(calls) == 2
    assert crawl_http.can_fetch("http://example.com/c")
    assert crawl_http.can_fetch("https://example.com:8443/c")
    assert len(calls) == 4


@pytest.mark.parametrize("adapter", [page_http, url_http])
@pytest.mark.parametrize("status", [200, 403])
def test_honest_agent_no_retry(monkeypatch, adapter, status):
    calls = []
    monkeypatch.setattr(crawl_http, "_open_robots", lambda *a, **k: response(404))
    def content(req, timeout):
        calls.append(req.full_url)
        assert req.get_header("User-agent") == crawl_http.USER_AGENT
        assert crawl_http.USER_AGENT.startswith("abbys-content-frame/")
        assert "Mozilla" not in crawl_http.USER_AGENT
        if status == 403:
            raise HTTPError(req.full_url, 403, "denied", {}, None)
        return response(200, b"article")
    monkeypatch.setattr(adapter, "urlopen", content)
    result = (adapter.HttpPageFetcher().fetch("https://example.com/x") if adapter is page_http
              else adapter.HttpUrlChecker().check("https://example.com/x", ["article"]))
    assert bool(result) is (status == 200)
    assert len(calls) == 1


@pytest.mark.parametrize("robots", [False, True])
def test_redirect_to_naver_blocked(robots):
    handler = crawl_http.PolicyRedirect(robots=robots)
    with pytest.raises(URLError):
        handler.redirect_request(Request("https://example.com"), None, 302, "", {}, "https://blog.naver.com/post")


def test_redirect_checks_destination_robots(monkeypatch):
    monkeypatch.setattr(crawl_http, "_open_robots", lambda *a, **k: response(200, b"User-agent: *\nDisallow: /private"))
    handler = crawl_http.PolicyRedirect()
    req = Request("https://example.com", headers={"User-Agent": crawl_http.USER_AGENT})
    with pytest.raises(URLError):
        handler.redirect_request(req, None, 302, "", {}, "https://other.com/private")
    redirected = handler.redirect_request(req, None, 302, "", {}, "https://other.com/public")
    assert redirected.get_header("User-agent") == crawl_http.USER_AGENT
