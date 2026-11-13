"""주제 설정과 준비 점검은 외부 CLI·네트워크 없이 검증합니다."""

import json
from http.client import HTTPException
import tomllib
from urllib.error import HTTPError, URLError

import pytest

from frame.cli import main
from frame.adapters import setup


@pytest.fixture
def topics():
    return dict(field="생활", region="울산", audience="이웃",
                seed_keywords=["정리", "산책", "장보기"], exclude=[],
                issue_sources=[], cadence_per_week=2)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for key in ("FRAME_ENGINE", "NAVER_HUB_CLIENT_ID", "NAVER_HUB_CLIENT_SECRET", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "DATA_GO_KR_SERVICE_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("frame.adapters.engines.shutil.which", lambda name: None)

    def no_network(*args, **kwargs):
        pytest.fail("테스트에서 실제 네트워크 요청을 시도했습니다.")

    monkeypatch.setattr(setup, "build_opener", no_network)


def test_topics_json_preserves_other_tables(tmp_path, topics):
    profile = tmp_path / "profile.toml"
    original = '# 내 설정\n[persona]\nname = "이웃"\ntext = """\n[topics]\n문자열\n"""\n\n[style]\ntone = "존댓말"\n'
    profile.write_text(original, encoding="utf-8", newline="\n")
    source = tmp_path / "topics.json"
    source.write_text(json.dumps(topics), encoding="utf-8")
    assert main(["setup", "topics", "--profile", str(profile), "--from-json", str(source)]) == 0
    saved = profile.read_text(encoding="utf-8")
    assert saved.startswith(original)
    parsed = tomllib.loads(saved)
    assert parsed["topics"] == topics
    assert parsed["persona"] == tomllib.loads(original)["persona"]
    assert b"\r" not in profile.read_bytes()
    topics["field"] = '생활 "정보" \\ 팁'
    source.write_text(json.dumps(topics), encoding="utf-8")
    assert main(["setup", "topics", "--profile", str(profile), "--from-json", str(source)]) == 0
    assert tomllib.loads(profile.read_text(encoding="utf-8"))["topics"] == topics


def test_topics_default_path_and_optional_lists(tmp_path, topics):
    del topics["issue_sources"]
    del topics["exclude"]
    source = tmp_path / "topics.json"
    source.write_text(json.dumps(topics), encoding="utf-8")
    config = tmp_path / "config"
    assert main(["setup", "topics", "--from-json", str(source)], config_dir=config) == 0
    saved = tomllib.loads((config / "profile.toml").read_text(encoding="utf-8"))
    assert saved["topics"]["issue_sources"] == []
    assert saved["topics"]["exclude"] == []


def test_new_profile_keeps_example_defaults_for_existing_commands(tmp_path, topics):
    from pathlib import Path
    from frame.config_loader import load_profile

    example = Path("config/profile.example.toml")
    (tmp_path / "profile.example.toml").write_bytes(example.read_bytes())
    source = tmp_path / "topics.json"
    source.write_text(json.dumps(topics), encoding="utf-8")
    assert main(["setup", "topics", "--from-json", str(source)], config_dir=tmp_path) == 0
    assert load_profile(tmp_path / "profile.toml") == load_profile(example)


@pytest.mark.parametrize("header", ["[topics]", '["topics"]'])
def test_replace_topics_between_other_tables(tmp_path, topics, header):
    profile = tmp_path / "profile.toml"
    profile.write_text(f'[persona]\nname = "이웃"\n{header}\nfield = "예전"\n[style]\ntone = "친근"\n', encoding="utf-8")
    setup.save_topics(profile, topics)
    assert tomllib.loads(profile.read_text(encoding="utf-8")) == {
        "persona": {"name": "이웃"}, "style": {"tone": "친근"}, "topics": topics}


@pytest.mark.parametrize("key,value", [
    ("field", " "), ("region", None), ("audience", 3), ("seed_keywords", ["가", "나"]),
    ("seed_keywords", ["가"] * 11), ("seed_keywords", "검색어"), ("exclude", [""]),
    ("issue_sources", ["ftp://example.org/feed"]), ("issue_sources", ["https://"]),
    ("cadence_per_week", 0), ("cadence_per_week", True), ("cadence_per_week", "2"),
])
def test_invalid_topics_leave_file_unchanged(tmp_path, topics, key, value):
    profile = tmp_path / "profile.toml"
    original = b'[persona]\nname = "test"\n'
    profile.write_bytes(original)
    topics[key] = value
    with pytest.raises(ValueError):
        setup.save_topics(profile, topics)
    assert profile.read_bytes() == original


@pytest.mark.parametrize("original", ['[broken', 'topics.field = "기존"\n'])
def test_unsupported_or_broken_toml_is_not_overwritten(tmp_path, topics, original):
    profile = tmp_path / "profile.toml"
    profile.write_text(original, encoding="utf-8", newline="\n")
    with pytest.raises(ValueError):
        setup.save_topics(profile, topics)
    assert profile.read_text(encoding="utf-8") == original


def test_interactive_retry_and_empty_sources(tmp_path, monkeypatch, capsys):
    answers = iter(["", "생활", "울산", "이웃", "하나,둘", "정리,산책,장보기", "", "", "두 편", "0", "2"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert main(["setup", "topics"], config_dir=tmp_path) == 0
    data = tomllib.loads((tmp_path / "profile.toml").read_text(encoding="utf-8"))["topics"]
    assert data["issue_sources"] == []
    assert data["cadence_per_week"] == 2
    assert "3~10개" in capsys.readouterr().out


def test_interactive_cancel_leaves_no_file(tmp_path, monkeypatch):
    def cancel(prompt):
        raise EOFError
    monkeypatch.setattr("builtins.input", cancel)
    assert main(["setup", "topics"], config_dir=tmp_path) == 1
    assert not (tmp_path / "profile.toml").exists()


@pytest.mark.parametrize("present", [False, True])
def test_doctor_env_never_prints_values(tmp_path, topics, monkeypatch, capsys, present):
    values = {key: f"fake-test-only-{index}" for index, key in enumerate(
        ("NAVER_HUB_CLIENT_ID", "NAVER_HUB_CLIENT_SECRET", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "DATA_GO_KR_SERVICE_KEY"))}
    if present:
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        setup.save_topics(tmp_path / "profile.toml", topics)
    assert main(["setup", "doctor"], config_dir=tmp_path) == 0
    output = capsys.readouterr().out
    for key, value in values.items():
        assert key in output
        assert value not in output
    assert ("NAVER_CLIENT_ID (유예(2027-06-30까지)) | 있음" if present else "NAVER_CLIENT_ID (유예(2027-06-30까지)) | 없음") in output
    assert ("프로필 [topics] | 준비됨" if present else "프로필 [topics] | 미완료") in output
    assert setup.GUIDE in output


@pytest.mark.parametrize("engine", ["claude", "codex"])
def test_doctor_reuses_engine_selection(tmp_path, monkeypatch, capsys, engine):
    monkeypatch.setattr("frame.adapters.engines.shutil.which", lambda name: name if name == engine else None)
    assert main(["setup", "doctor"], config_dir=tmp_path) == 0
    assert f"선택 엔진 | {engine}" in capsys.readouterr().out


@pytest.mark.parametrize("contents", ["[broken", '[topics]\nfield = "생활"', ""])
def test_doctor_incomplete_profile_always_zero(tmp_path, contents, capsys, monkeypatch):
    monkeypatch.setenv("FRAME_ENGINE", "invalid")
    profile = tmp_path / "selected.toml"
    profile.write_text(contents, encoding="utf-8")
    assert main(["setup", "doctor", "--profile", str(profile)]) == 0
    output = capsys.readouterr().out
    assert "미완료" in output
    assert "선택 엔진 | 없음" in output


@pytest.mark.parametrize("status,expected", [(200, "OK"), (401, "HTTP 401")])
def test_check_naver_fake_transport(tmp_path, monkeypatch, capsys, status, expected):
    monkeypatch.setenv("NAVER_CLIENT_ID", "fake-test-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "fake-test-secret")
    calls = []

    class FakeTransport:
        def post(self, url, headers, body):
            calls.append((url, headers, json.loads(body)))
            return status

    assert main(["setup", "doctor", "--check-naver"], config_dir=tmp_path, naver_transport=FakeTransport()) == 0
    assert len(calls) == 1
    assert calls[0][0] == setup.NAVER_URL
    assert calls[0][1]["X-Naver-Client-Secret"] == "fake-test-secret"
    assert calls[0][2]["keywordGroups"][0]["keywords"] == ["생활"]
    output = capsys.readouterr().out
    assert f"네이버 연결 | {expected}" in output
    assert "fake-test-id" not in output and "fake-test-secret" not in output


def test_check_naver_missing_keys_skips_request(tmp_path, capsys):
    assert main(["setup", "doctor", "--check-naver"], config_dir=tmp_path) == 0
    assert "건너뜀" in capsys.readouterr().out


@pytest.mark.parametrize("error", [URLError, HTTPException])
def test_network_failure_does_not_leak_exception(tmp_path, monkeypatch, capsys, error):
    monkeypatch.setenv("NAVER_CLIENT_ID", "fake-test-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "fake-test-secret")

    class FakeTransport:
        def post(self, *args):
            raise error("fake-test-secret")

    assert main(["setup", "doctor", "--check-naver"], config_dir=tmp_path, naver_transport=FakeTransport()) == 0
    output = capsys.readouterr().out
    assert "연결 실패" in output and "fake-test-secret" not in output


@pytest.mark.parametrize("status", [200, 401])
def test_http_transport_posts_once_without_redirects(monkeypatch, status):
    calls = []

    class Response:
        def __enter__(self):
            self.status = status
            return self

        def __exit__(self, *args):
            pass

    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            assert timeout == 10
            if status == 401:
                raise HTTPError(request.full_url, 401, "오류", {}, None)
            return Response()

    def opener(handler):
        assert handler.redirect_request(None, None, 302, "", {}, "https://example.org") is None
        return Opener()

    monkeypatch.setattr(setup, "build_opener", opener)
    assert setup.HttpNaverTransport().post(setup.NAVER_URL, {}, b"{}") == status
    assert len(calls) == 1
    assert calls[0].get_method() == "POST"
    assert calls[0].data == b"{}"


@pytest.mark.parametrize("present", [False, True])
def test_doctor_hub_rows_and_preferred_request(tmp_path, monkeypatch, capsys, present):
    for name in setup.NAVER_KEY_NAMES[2:]:
        monkeypatch.setenv(name, "fake-legacy-" + name)
    if present:
        for name in setup.NAVER_KEY_NAMES[:2]:
            monkeypatch.setenv(name, "fake-hub-" + name)
    calls = []
    class FakeTransport:
        def post(self, url, headers, body):
            calls.append((url, headers))
            return 200
    assert setup.doctor(tmp_path / "missing.toml", check_naver=True, transport=FakeTransport()) == 0
    output = capsys.readouterr().out
    for name in setup.NAVER_KEY_NAMES[:2]:
        assert f"{name} (권장) | {'있음' if present else '없음'}" in output
    for name in setup.NAVER_KEY_NAMES[2:]:
        assert f"{name} (유예(2027-06-30까지)) | 있음" in output
    assert len(calls) == 1
    assert calls[0][0] == (setup.NAVER_HUB_URL if present else setup.NAVER_URL)
    if present:
        assert calls[0][1]["X-NCP-APIGW-API-KEY-ID"] == "fake-hub-NAVER_HUB_CLIENT_ID"
        assert calls[0][1]["X-NCP-APIGW-API-KEY"] == "fake-hub-NAVER_HUB_CLIENT_SECRET"
        assert "X-Naver-Client-Id" not in calls[0][1]
    assert "fake-hub-" not in output and "fake-legacy-" not in output
