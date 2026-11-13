import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from frame.adapters import claude_judge, page_http


@pytest.fixture(autouse=True)
def allow_test_pages(monkeypatch):
    monkeypatch.setattr(page_http, "can_fetch", lambda url: True)


@pytest.mark.parametrize("encoding", ["utf-8", "cp949"])
def test_fetch_cleans_html(monkeypatch, encoding):
    class Response:
        status = 200
        headers = {"Content-Type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return '<STYLE>숨김</STYLE><script>숨김</script><p>보습&nbsp; 관리</p>'.encode(encoding)

    def urlopen(url, timeout):
        assert url.full_url == "https://example.com" and timeout == 20
        assert url.get_header("User-agent").startswith("abbys-content-frame/")
        return Response()

    monkeypatch.setattr(page_http, "urlopen", urlopen)
    assert page_http.HttpPageFetcher().fetch("https://example.com") == "보습 관리"


@pytest.mark.parametrize("status,raw,expected", [
    (201, b"text", None), (200, b"\xff", None), (200, b"a" * 30001, "a" * 30000),
], ids=["non-ok", "invalid-encoding", "truncate-long-page"])
def test_fetch_boundaries(monkeypatch, status, raw, expected):
    from contextlib import nullcontext

    monkeypatch.setattr(page_http, "urlopen", lambda *a, **k: nullcontext(
        SimpleNamespace(status=status, headers={}, read=lambda: raw)))
    assert page_http.HttpPageFetcher().fetch("https://example.com") == expected


def test_fetch_skips_pdf_and_prefers_article(monkeypatch):
    from contextlib import nullcontext

    assert page_http.HttpPageFetcher().fetch("https://example.com/report.PDF") is None
    monkeypatch.setattr(page_http, "urlopen", lambda *a, **k: nullcontext(SimpleNamespace(
        status=200, headers={"Content-Type": "application/pdf"}, read=lambda: b"%PDF")))
    assert page_http.HttpPageFetcher().fetch("https://example.com/download") is None
    html = "<nav>메뉴</nav><p>광고</p><article><p>습도 40~60%</p></article><footer>저작권</footer>"
    assert page_http.html_to_text(html) == "습도 40~60%"


def test_fetch_error(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("연결 실패")

    monkeypatch.setattr(page_http, "urlopen", fail)
    assert page_http.HttpPageFetcher().fetch("https://example.com") is None


@pytest.mark.parametrize("stdout,verdict", [
    ('설명\n```json\n' + json.dumps({"verdict": "supports", "evidence": "문장 {인용}", "reason": "일치"}) + '\n```', "supports"),
    ("JSON 아님", "unrelated"), ('{"verdict": "supports"}', "unrelated"),
    ('{"verdict": "unknown", "evidence": "", "reason": ""}', "unrelated"),
])
def test_judge_stdin_and_json(monkeypatch, stdout, verdict):
    directories = []
    monkeypatch.setattr(claude_judge.shutil, "which", lambda name: "resolved-claude")

    def run(command, **kwargs):
        assert command == ["resolved-claude", "-p", "--model", "sonnet", "--output-format", "text"]
        assert all(value in kwargs["input"] for value in ("제목 자료", "본문 자료", "출처 자료", "페이지 자료"))
        path = Path(kwargs["cwd"])
        assert path.is_dir() and not list(path.iterdir())
        directories.append(path)
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(claude_judge.subprocess, "run", run)
    result = claude_judge.ClaudeCliJudge().judge("제목 자료", "본문 자료", "출처 자료", "페이지 자료")
    assert result["verdict"] == verdict
    if verdict == "unrelated":
        assert result["reason"] == "판정 응답을 읽지 못함"
    assert not directories[0].exists()


@pytest.mark.parametrize("missing", [True, False])
def test_judge_execution_error(monkeypatch, missing):
    monkeypatch.setattr(claude_judge.shutil, "which", lambda name: None)

    def run(command, **kwargs):
        assert command[0] == "claude"
        if missing:
            raise OSError("설치 안 됨")
        return SimpleNamespace(returncode=1, stderr="실행 실패")

    monkeypatch.setattr(claude_judge.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="Claude CLI"):
        claude_judge.ClaudeCliJudge().judge("", "", "", "")
