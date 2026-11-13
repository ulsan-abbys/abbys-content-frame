"""사전 조사는 실제 HTTP·AI 호출 없이 검증합니다."""

from datetime import date
import json
from pathlib import Path

import pytest

from frame.adapters.research import fetch_demand, fetch_issues, HttpResearchTransport, run_research
from frame.adapters.setup import save_topics
from frame.cli import main
from frame.core.research import topic_prompt, validate_candidates


@pytest.fixture
def topics():
    return dict(field="생활", region="울산", audience="이웃", seed_keywords=["산책", "정리", "장보기"],
                exclude=["가격"], issue_sources=["https://example.org/rss"], cadence_per_week=2)


@pytest.fixture(autouse=True)
def no_keys(monkeypatch):
    for name in ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)


class Transport:
    def __init__(self, status=200, body=None):
        self.calls = []
        self.status = status
        self.body = body

    def request(self, method, url, headers, body=None):
        self.calls.append((method, url, headers, body))
        if method == "GET":
            return 200, Path("tests/fixtures/research.rss").read_bytes()
        return self.status, json.dumps(self.body or {
            "results": [{"title": "산책", "data": [{"period": "2026-11-09", "ratio": 100}]}]
        }).encode()


def candidate(evidence=None, **kwargs):
    return dict(title="산책 준비", reader_situation="울산 이웃", why_now="지역 소식 확인",
                evidence=["https://example.org/walk"] if evidence is None else evidence,
                excluded_check="제외 주제 없음", **kwargs)


class Writer:
    def __init__(self):
        self.calls = []

    def write(self, prompt, workdir):
        self.calls.append(prompt)
        return json.dumps([candidate()], ensure_ascii=False)


def test_rss_filter_dedupe_and_no_sources(topics):
    transport = Transport()
    topics["issue_sources"] *= 2
    status, items, _ = fetch_issues(topics, transport)
    assert status == "done"
    assert [i["title"] for i in items] == ["산책 소식", "지역 알림"]
    assert set(items[0]) == {"title", "link", "published", "source", "fetched_at"}
    assert len(transport.calls) == 1
    assert transport.calls[0][0] == "GET"
    assert transport.calls[0][2]["User-Agent"] == "abbys-content-frame/0.x"
    topics["issue_sources"] = []
    status, items, note = fetch_issues(topics, transport)
    assert status == "skipped" and not items and "API_키_발급_가이드.md" in note


def test_atom_summary_and_relative_links(topics):
    class Atom:
        def request(self, *args):
            return 200, b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
                <title>News</title><summary>walk</summary><link href="/walk"/>
                <updated>2026-11-01</updated></entry></feed>'''
    topics["seed_keywords"] = ["walk"]
    status, items, _ = fetch_issues(topics, Atom())
    assert status == "done" and items[0]["link"] == "https://example.org/walk"
    assert items[0]["published"] == "2026-11-01"


def test_datalab_request_and_missing_keys(topics, monkeypatch):
    transport = Transport()
    assert fetch_demand(topics, transport)[0] == "skipped"
    assert not transport.calls
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-only-client")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-only-secret")
    topics["seed_keywords"] += ["요리", "청소", "운동"]
    status, items, _ = fetch_demand(topics, transport, today=date(2026, 11, 14))
    assert status == "done" and items[0]["unit"] == "상대지수(0~100)"
    method, url, headers, raw = transport.calls[0]
    request = json.loads(raw)
    assert method == "POST" and url == "https://openapi.naver.com/v1/datalab/search"
    assert headers["X-Naver-Client-Id"] == "test-only-client"
    assert request["timeUnit"] == "week" and len(request["keywordGroups"]) == 5
    assert (date.fromisoformat(request["endDate"]) - date.fromisoformat(request["startDate"])).days == 83
    assert items[0]["ratio"][0]["ratio"] == 100


def test_401_permission_and_keys_never_saved(topics, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-only-client")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-only-secret")
    transport = Transport(401, {"errorCode": "024", "errorMessage": "test-only-secret"})
    status, _, note = fetch_demand(topics, transport)
    assert status == "failed" and "권한이 없음 — 앱 Client ID 확인" in note
    profile = tmp_path / "profile.toml"
    save_topics(profile, topics)
    class FailingWriter:
        def write(self, *args):
            raise RuntimeError("test-only-client test-only-secret")
    assert main(["research", "--profile", str(profile), "--out", str(tmp_path / "runs")],
                writer=FailingWriter(), research_transport=transport) == 1
    texts = capsys.readouterr().out + "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "runs").iterdir())
    assert "test-only-client" not in texts and "test-only-secret" not in texts


def test_validation_and_prompt(topics):
    issues = [{"link": "https://example.org/walk"}]
    bad = candidate()
    bad["title"] = "산책 가격 안내"
    values = [candidate([]), candidate(["invented"]), candidate(["산책", "invented"]), bad,
              candidate(["산책"]), candidate()]
    accepted = validate_candidates(json.dumps(values), topics, issues, [{"keyword": "산책"}])
    assert len(accepted) == 2
    topics["cadence_per_week"] = 10
    assert len(validate_candidates(json.dumps([candidate()] * 10), topics, issues, [])) == 6
    prompt = topic_prompt(topics, issues, [])
    assert "최대 6개" in prompt and all(k in prompt for k in topics)


def test_resume_done_nodes_and_cli(topics, tmp_path, capsys):
    profile = tmp_path / "profile.toml"
    save_topics(profile, topics)
    transport, writer = Transport(), Writer()
    out = tmp_path / "runs"
    assert main(["research", "--profile", str(profile), "--out", str(out), "--skip", "N2"],
                writer=writer, research_transport=transport) == 0
    path = next(p for p in out.glob("*.json") if p.name.count(".") == 1)
    state = json.loads(path.read_text(encoding="utf-8"))
    assert [r["status"] for r in state["nodes"].values()] == ["done", "skipped", "done"]
    assert all(r["started_at"] and r["finished_at"] for r in state["nodes"].values())
    profile.unlink()
    assert main(["research", "--resume", str(path), "--skip", "N2"],
                writer=writer, research_transport=transport) == 0
    assert len(writer.calls) == len(transport.calls) == 1
    assert "frame write --topic" in capsys.readouterr().out
    assert "G1" in path.with_suffix(".topics.md").read_text(encoding="utf-8")
    assert all(b"\r\n" not in p.read_bytes() for p in out.iterdir())


def test_failed_engine_is_resumable(topics, tmp_path):
    def unavailable():
        raise RuntimeError("설치 필요")
    transport = Transport()
    path, state, _ = run_research(topics, tmp_path, unavailable, transport, skip="N2")
    assert state["nodes"]["N3"]["status"] == "failed"
    assert "설치" in state["nodes"]["N3"]["note"]
    _, state, candidates = run_research(None, tmp_path, Writer, transport, resume=path, skip="N2")
    assert state["nodes"]["N3"]["status"] == "done" and candidates
    assert len(transport.calls) == 1


def test_real_transport_request_contract(monkeypatch):
    import frame.adapters.research as module
    calls = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b"ok"
    class Opener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            return Response()
    monkeypatch.setattr(module, "can_fetch", lambda url: True)
    monkeypatch.setattr(module, "build_opener", lambda *args: Opener())
    assert HttpResearchTransport().request("GET", "https://example.org/rss", {}) == (200, b"ok")
    assert len(calls) == 1 and calls[0][1] == 10 and calls[0][0].get_method() == "GET"


@pytest.mark.parametrize("engine", ["auto", "claude", "codex"])
def test_cli_selects_existing_engine_pattern(engine, topics, tmp_path, monkeypatch):
    import frame.cli as cli
    selected = []
    def select(requested):
        selected.append(requested)
        return "codex" if requested == "codex" else "claude"
    monkeypatch.setattr(cli, "select_engine", select)
    monkeypatch.setattr(cli, "CodexCliWriter", Writer)
    monkeypatch.setattr(cli, "ClaudeCliWriter", lambda **kwargs: Writer())
    profile = tmp_path / "profile.toml"
    save_topics(profile, topics)
    assert main(["research", "--profile", str(profile), "--out", str(tmp_path / "runs"),
                 "--engine", engine], research_transport=Transport()) == 0
    assert selected == [engine]


def test_feed_failures_and_no_valid_candidates(topics, tmp_path):
    class InvalidFeed:
        def request(self, *args):
            return 200, b"not XML"
    assert fetch_issues(topics, InvalidFeed())[0] == "failed"
    class Uncited:
        def write(self, *args):
            return json.dumps([candidate([])])
    path, state, values = run_research(topics, tmp_path, Uncited, Transport())
    assert state["nodes"]["N3"]["status"] == "failed" and not values
    assert path.with_suffix(".topics.md").exists()


def test_partial_feed_failure_preserves_evidence(topics):
    topics["issue_sources"].append("https://example.org/broken")
    class Partial(Transport):
        def request(self, method, url, headers, body=None):
            if url.endswith("broken"):
                return 503, b""
            return super().request(method, url, headers, body)
    status, items, note = fetch_issues(topics, Partial())
    assert status == "done" and items and "실패 1개" in note


def test_transport_401_body_and_policy_denial(monkeypatch):
    import io
    from urllib.error import HTTPError
    import frame.adapters.research as module
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            raise HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"errorCode":"024"}'))
    monkeypatch.setattr(module, "build_opener", lambda *args: Opener())
    monkeypatch.setattr(module, "can_fetch", lambda url: False)
    transport = HttpResearchTransport()
    assert transport.request("GET", "https://example.org/rss", {}) == (403, b"")
    assert not calls
    status, body = transport.request("POST", "https://openapi.naver.com/v1/datalab/search", {}, b"{}")
    assert status == 401 and json.loads(body)["errorCode"] == "024" and len(calls) == 1
