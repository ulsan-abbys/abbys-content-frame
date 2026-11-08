import json
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from frame import cli
from frame.adapters import codex_cli, engines
from frame.adapters.judge_response import parse_judgment
from frame.config_loader import load_profile, load_writing_profile, resolve_profile
from frame.core.pipeline import run_write_loop

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"


@pytest.mark.parametrize("installed,expected", [
    ({"claude", "codex"}, "claude"), ({"claude"}, "claude"), ({"codex"}, "codex"),
])
def test_auto_engine(monkeypatch, installed, expected):
    monkeypatch.delenv("FRAME_ENGINE", raising=False)
    monkeypatch.setattr(engines.shutil, "which", lambda name: name if name in installed else None)
    assert engines.select_engine() == expected


def test_engine_environment_and_override(monkeypatch):
    monkeypatch.setattr(engines.shutil, "which", lambda name: name)
    monkeypatch.setenv("FRAME_ENGINE", "codex")
    assert engines.select_engine() == "codex"
    assert engines.select_engine("claude") == "claude"
    assert engines.select_engine("auto") == "claude"
    monkeypatch.setenv("FRAME_ENGINE", "invalid")
    with pytest.raises(engines.EngineUnavailable):
        engines.select_engine()
    monkeypatch.setattr(engines.shutil, "which", lambda name: "codex" if name == "codex" else None)
    with pytest.raises(engines.EngineUnavailable):
        engines.select_engine("claude")


@pytest.mark.parametrize("command", [["write", ".", "--topic", "생활"], ["write", "."], ["score", "missing.md"]])
def test_missing_engines_exit_two(monkeypatch, capsys, command):
    monkeypatch.delenv("FRAME_ENGINE", raising=False)
    monkeypatch.setattr(engines.shutil, "which", lambda name: None)
    assert cli.main(command, config_dir=CONFIG) == 2
    assert "Claude Code 또는 Codex CLI 중 하나를 설치하고 로그인하세요" in capsys.readouterr().out


@pytest.mark.parametrize("judge", [False, True])
def test_codex_command_and_last_message(monkeypatch, tmp_path, judge):
    monkeypatch.setattr(codex_cli.shutil, "which", lambda name: "codex.cmd")
    directories, outputs = [], []
    reply = json.dumps({"verdict": "supports", "evidence": "문장", "reason": "일치"})

    def run(command, **kwargs):
        output = Path(command[command.index("--output-last-message") + 1])
        directory = Path(kwargs["cwd"])
        assert command == ["codex.cmd", "exec", "--skip-git-repo-check", "-s",
                           "read-only", "-C", str(directory.resolve()),
                           "-c", "web_search=disabled" if judge else "web_search=live",
                           "--output-last-message", str(output), "-"]
        assert "\n" in kwargs["input"] and kwargs["encoding"] == "utf-8"
        assert kwargs.get("shell", False) is False
        if judge:
            assert directory != tmp_path and not list(directory.iterdir())
            assert all(value in kwargs["input"] for value in ("제목", "본문", "출처", "페이지"))
        else:
            assert kwargs["input"] == "첫 줄\n두 번째 줄"
        directories.append(directory)
        outputs.append(output)
        output.write_text(reply, encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="진행 로그", stderr="")

    monkeypatch.setattr(codex_cli.subprocess, "run", run)
    if judge:
        assert codex_cli.CodexCliJudge().judge("제목", "본문", "출처", "페이지")["verdict"] == "supports"
        assert not directories[0].exists()
    else:
        assert codex_cli.CodexCliWriter().write("첫 줄\n두 번째 줄", str(tmp_path)) == reply
        assert directories[0].exists()
    assert not outputs[0].exists()


@pytest.mark.parametrize("failure", ["missing", "exit", "no-output", "empty-output"])
def test_codex_failure(monkeypatch, tmp_path, failure):
    monkeypatch.setattr(codex_cli.shutil, "which", lambda name: None)

    def run(command, **kwargs):
        assert command[0] == "codex"
        if failure == "missing":
            raise OSError("설치 안 됨")
        if failure == "empty-output":
            Path(command[-2]).write_text(" ", encoding="utf-8")
        return SimpleNamespace(returncode=int(failure == "exit"), stdout="진행 로그", stderr="실행 실패")

    monkeypatch.setattr(codex_cli.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="Codex CLI"):
        codex_cli.CodexCliWriter().write("초안", str(tmp_path))


@pytest.mark.parametrize("text", ["null", "[]", "```json\n{}\n```", '{"verdict":"supports","evidence":1,"reason":""}'])
def test_common_judgment_parser_rejects_invalid_response(text):
    assert parse_judgment(text)["verdict"] == "unrelated"


def test_new_workspace_and_no_overwrite(tmp_path, capsys):
    directory = tmp_path / "내 블로그"
    name = '작가 "새봄"\n두 줄'
    assert cli.main(["new", str(directory), "--field", "원예", "--name", name,
                     "--region", "부산"], config_dir=CONFIG) == 0
    assert {p.name for p in directory.iterdir()} == {"profile.toml", "AGENTS.md", "STATE.md", "초안"}
    spec, persona, packs, _ = load_profile(directory / "profile.toml")
    assert (persona["name"], persona["field"], persona["region"]) == (name, "원예", "부산")
    assert packs == ["general_ko"] and re.search(spec.human_slot_pattern, "[내 경험]")
    agents = (directory / "AGENTS.md").read_text(encoding="utf-8")
    assert all(word in agents for word in ("1200~1800", "소제목", "출처", "[내 경험]", "지어내", "과장"))
    before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    assert cli.main(["new", str(directory)], config_dir=CONFIG) == 1
    assert before == {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    occupied = tmp_path / "file"
    occupied.write_text("보존", encoding="utf-8")
    assert cli.main(["new", str(occupied)], config_dir=CONFIG) == 1
    assert occupied.read_text(encoding="utf-8") == "보존"


def test_profile_precedence_and_default_slot(tmp_path):
    config, work = tmp_path / "config", tmp_path / "work"
    config.mkdir()
    work.mkdir()
    base = (CONFIG / "profile.example.toml").read_text(encoding="utf-8")
    fallback = config / "profile.example.toml"
    fallback.write_text(base, encoding="utf-8")
    assert resolve_profile(None, config, str(work)) == fallback
    custom = config / "profile.toml"
    custom.write_text(base, encoding="utf-8")
    assert resolve_profile(None, config, str(work)) == custom
    local = work / "profile.toml"
    local.write_text(re.sub(r"(?m)^human_slot_pattern = .*\n", "", base).replace("내 경험", "정원 기록"), encoding="utf-8")
    assert resolve_profile(None, config, str(work)) == local
    assert resolve_profile(str(fallback), config, str(work)) == fallback
    assert re.search(load_profile(local)[0].human_slot_pattern, "[정원 기록]")


def test_profile_in_initial_and_rewrite_prompts():
    profile = load_writing_profile(CONFIG / "profile.example.toml")
    prompts = []
    run_write_loop("정리", "초안.md",
                   lambda prompt: (prompts.append(prompt) or "<<<DRAFT\n본문\nDRAFT>>>"), lambda text: None,
                   lambda text: (False, {}, []), lambda text: (False, 0, 2, []),
                   lambda record: None, 1, clock=lambda: 0, profile=profile)
    assert len(prompts) == 2
    for prompt in prompts:
        assert "의료법" not in prompt and "건강정보" not in prompt and "[원장 경험]" not in prompt
        assert all(value in prompt for value in profile.persona.values())
        assert profile.style["tone"] in prompt and "이모지 사용 금지" in prompt
        assert "[내 경험]" in prompt and profile.checklist in prompt
    assert profile.genre in prompts[0]


def test_write_uses_workspace_profile(monkeypatch, tmp_path):
    from test_pipeline import FakeFetcher, FileWriter, FakeJudge

    content = (CONFIG / "profile.example.toml").read_text(encoding="utf-8")
    content = (content.replace("생활 정보", "원예 수필").replace("내 경험", "정원 기록")
               .replace("AGENTS.md의 점검표", "원예 점검표").replace("forbid_emoji = true", "forbid_emoji = false"))
    (tmp_path / "profile.toml").write_text(content, encoding="utf-8")
    good = (ROOT / "tests/fixtures/good.md").read_text(encoding="utf-8").replace("내 경험", "정원 기록")
    writer = FileWriter([good])
    # 포트를 모두 주입한 실행은 설치된 CLI나 환경변수에 의존하지 않습니다.
    monkeypatch.setattr(engines.shutil, "which", lambda name: None)
    assert cli.main(["write", str(tmp_path), "--topic", "정원"], writer=writer,
                    judge=FakeJudge(), fetcher=FakeFetcher(), config_dir=CONFIG) == 0
    assert all(value in writer.prompts[0] for value in
               ("원예 수필", "[정원 기록]", "원예 점검표", "이모지 사용 허용"))


@pytest.mark.parametrize("engine", ["claude", "codex"])
def test_only_one_engine_write_and_score(monkeypatch, tmp_path, capsys, engine):
    from test_pipeline import FakeFetcher, FileWriter, FakeJudge

    monkeypatch.delenv("FRAME_ENGINE", raising=False)
    monkeypatch.setattr(engines.shutil, "which", lambda name: name if name == engine else None)
    writer = FileWriter([(ROOT / "tests/fixtures/good.md").read_text(encoding="utf-8")])
    prefix = "Claude" if engine == "claude" else "Codex"
    monkeypatch.setattr(cli, prefix + "CliWriter", lambda: writer)
    monkeypatch.setattr(cli, prefix + "CliJudge", FakeJudge)
    assert cli.main(["write", str(tmp_path), "--topic", "생활", "--draft", "초안.md"],
                    config_dir=CONFIG, fetcher=FakeFetcher()) == 0
    assert capsys.readouterr().out.splitlines()[0] == f"엔진: {engine}"
    assert cli.main(["score", str(tmp_path / "초안.md")], config_dir=CONFIG, fetcher=FakeFetcher()) == 0
    assert capsys.readouterr().out.splitlines()[0] == f"엔진: {engine}"
