import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from frame.adapters import claude_cli
from frame.adapters.write_workspace import WriteWorkspace
from frame.cli import main
from frame.core.pipeline import run_write_loop
from frame.core.scoring import parse_draft, score_sources

ROOT = Path(__file__).resolve().parents[1]
PAGE = "보습제는 수분 함량에 따라 로션, 크림, 연고로 나뉩니다. 피부가 건조하면 보습제를 꾸준히 사용하는 것이 도움이 됩니다."


@pytest.mark.parametrize("evidence,passed", [
    ("보습제는 로션, 크림, 연고로 나뉩니다. 피부가 건조하면 보습제를 꾸준히 사용하는 것이 도움이 됩니다.", True),
    ("보습제는 로션, 크림, 연고로 나뉩니다.", False),
    ("이 페이지에 없는 완전히 지어낸 문장으로 근거를 주장합니다.", False),
    ("짧은 문장", False),
    ("피부가건조하면, 보습제를 꾸준히 사용하는 것이 도움이 됩니다!", True),
])
def test_evidence_sentences(evidence, passed):
    result = score_sources(parse_draft("# 보습\n## 출처\n- 안내: https://example.com"),
                           lambda url: PAGE + " 짧은 문장",
                           lambda *args: {"verdict": "supports", "evidence": evidence, "reason": "일치"}, 1)
    assert result.passed is passed
    if not passed:
        assert result.verdicts[0].reason == "근거 문장이 페이지에 없음"


@pytest.mark.parametrize("separator", [".", "!", "?", "。", "\n", "\r\n"])
def test_sentence_separators(separator):
    result = score_sources(parse_draft("## 출처\n- 안내: https://example.com"), lambda url: PAGE,
                           lambda *args: {"verdict": "supports", "evidence": "잘못된 인용" + separator + PAGE,
                                          "reason": "일치"}, 1)
    assert result.passed


class FakeFetcher:
    def fetch(self, url):
        return PAGE


class FakeJudge:
    def judge(self, title, body, label, page):
        return {"verdict": "unrelated" if "실패표식" in body else "supports",
                "evidence": PAGE, "reason": "주제 판정"}


class FileWriter:
    def __init__(self, drafts):
        self.drafts = drafts
        self.prompts = []

    def write(self, prompt, workdir):
        self.prompts.append(prompt)
        content = self.drafts[min(len(self.prompts) - 1, len(self.drafts) - 1)]
        return f"<<<DRAFT\n{content}\nDRAFT>>>" if content is not None else "초안 없음"



@pytest.mark.parametrize("mode,count,code", [("pass", 1, 0), ("retry", 2, 0),
                                            ("fail", 3, 1), ("missing", 1, 1)])
def test_write_integration(tmp_path, capsys, mode, count, code):
    good = (ROOT / "tests/fixtures/good.md").read_text(encoding="utf-8")
    bad = "# 실패표식\n## 출처\n- 안내: https://example.com\n"
    drafts = {"pass": [good], "retry": [bad, good], "fail": [bad], "missing": [None]}[mode]
    writer = FileWriter(drafts)
    (tmp_path / "AGENTS.md").write_text("고유한 작업 지침 전문", encoding="utf-8")
    (tmp_path / "STATE.md").write_text("기존 상태", encoding="utf-8")
    assert main(["write", str(tmp_path), "--topic", "겨울 보습!"], writer=writer,
                fetcher=FakeFetcher(), judge=FakeJudge(), config_dir=ROOT / "config") == code
    output = capsys.readouterr().out
    assert "완료" not in output and "—" not in output
    assert all("고유한 작업 지침 전문" in prompt for prompt in writer.prompts)
    state = (tmp_path / "STATE.md").read_text(encoding="utf-8")
    assert state.startswith("기존 상태\n- ")
    assert state.endswith(f"초안 초안/01_겨울-보습.md: 기계 점검 {'통과' if code == 0 else '실패'}, 라운드 {count - 1}\n")
    if mode != "missing":
        assert (tmp_path / "초안/01_겨울-보습.md").read_text(encoding="utf-8") == drafts[-1].strip()
    assert len(writer.prompts) == count
    records = [json.loads(line) for line in (tmp_path / "logs/write_runs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(records) == count
    assert [r["round"] for r in records] == list(range(count))
    assert records[0]["topic"] == "겨울 보습!"
    assert records[0]["draft"] == "초안/01_겨울-보습.md"
    assert records[0]["timestamp"] and records[0]["seconds"] >= 0
    if mode == "retry":
        assert records[0]["findings"] and records[0]["verdict_lines"]
        for line in records[0]["findings"] + records[0]["verdict_lines"]:
            assert line in writer.prompts[1]
        assert not records[0]["check_passed"] and not records[0]["score_passed"]
    if code == 0:
        assert output.rstrip().endswith("기계 점검 통과 - 사람 검수 대기 (G2): 초안/01_겨울-보습.md")
    elif mode == "missing":
        assert "초안 파일이 없습니다" in output
    else:
        assert "최대 고쳐 쓰기 2회" in output


def test_numbering_slug_and_path(tmp_path):
    folder = tmp_path / "초안"
    folder.mkdir()
    for name in ["01_예시.md", "09_예시.md", "잘못된.md"]:
        (folder / name).touch()
    (folder / "99_폴더").mkdir()
    assert WriteWorkspace(str(tmp_path), "  보습 & Skin 2!?  ".strip(), None).draft_rel == "초안/10_보습--Skin-2.md"
    assert WriteWorkspace(str(tmp_path), "보습", "다른/초안.md").draft_rel == "다른/초안.md"
    with pytest.raises(ValueError):
        WriteWorkspace(str(tmp_path), "보습", "../outside.md")


def test_clock_and_rewrite_limit():
    prompts, records = [], []
    ticks = iter([1.0, 3.5])
    outcome = run_write_loop("보습", "초안.md",
                             lambda prompt: (prompts.append(prompt) or "<<<DRAFT\n본문\nDRAFT>>>"), lambda text: None,
                             lambda text: (True, {}, []), lambda text: (False, 0, 2, ["출처 부족"]),
                             records.append, 0, clock=lambda: next(ticks))
    assert not outcome.passed and not outcome.draft_missing
    assert len(prompts) == 1 and records[0].seconds == 2.5
    with pytest.raises(ValueError):
        run_write_loop("보습", "초안.md", prompts.append, lambda text: None, None, None,
                       records.append, -1, clock=lambda: 0)
    assert len(prompts) == 1


def test_writer_allowed_tools(monkeypatch):
    monkeypatch.setattr(claude_cli.shutil, "which", lambda name: "resolved-claude")

    def run(command, **kwargs):
        assert command == ["resolved-claude", "-p", "--model", "sonnet",
                           "--allowedTools", "WebSearch", "WebFetch"]
        # The prompt goes on stdin: claude.cmd cuts arguments at the first newline.
        assert kwargs["input"] == "프롬프트"
        assert kwargs["cwd"] == "작업폴더"
        return SimpleNamespace(returncode=0, stdout="응답")

    monkeypatch.setattr(claude_cli.subprocess, "run", run)
    assert claude_cli.ClaudeCliWriter().write("프롬프트", "작업폴더") == "응답"


@pytest.mark.parametrize("profile_mode", ["fallback", "default", "explicit"])
def test_write_profile_and_append(tmp_path, monkeypatch, profile_mode):
    import shutil

    config = tmp_path / "frame-config"
    shutil.copytree(ROOT / "config", config)
    base = (config / "profile.example.toml").read_text(encoding="utf-8")
    args = []
    if profile_mode == "default":
        (config / "profile.toml").write_text(base.replace("min_sources = 2", "min_sources = 3"), encoding="utf-8")
    elif profile_mode == "explicit":
        custom = config / "custom.toml"
        custom.write_text(base.replace("min_sources = 2", "min_sources = 3"), encoding="utf-8")
        args = ["--profile", str(custom)]
    monkeypatch.chdir(tmp_path)
    good = (ROOT / "tests/fixtures/good.md").read_text(encoding="utf-8")
    writer = FileWriter([good])
    expected = 0 if profile_mode == "fallback" else 1
    for _ in range(2):
        assert main(["write", str(tmp_path), "--topic", "보습", "--draft", "지정.md",
                     "--max-rewrites", "0", *args], writer=writer, fetcher=FakeFetcher(),
                    judge=FakeJudge(), config_dir=config) == expected
    records = [json.loads(line) for line in (tmp_path / "logs/write_runs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2 and len(writer.prompts) == 2
    assert all(r["draft"] == "지정.md" and r["required"] == (2 if expected == 0 else 3) for r in records)


def test_rewrite_prompt_includes_measured_values():
    prompts = []
    drafts = iter(["짧은 본문", "고친 본문"])
    outcome = run_write_loop(
        "보습", "초안.md", lambda prompt: (prompts.append(prompt) or f"<<<DRAFT\n{next(drafts)}\nDRAFT>>>"), lambda text: None,
        lambda text: (text == "고친 본문", {"chars": 812, "headings": 2},
                      ["본문 공백 제외 글자 수는 1000~1800자여야 합니다."]),
        lambda text: (True, 2, 2, []), lambda record: None, 1, clock=lambda: 0.0,
    )
    assert outcome.passed and len(prompts) == 2
    assert "현재 측정값: chars=812, headings=2" in prompts[1]
    assert "1000~1800자" in prompts[1]
    assert "짧은 본문" in prompts[1]

@pytest.mark.parametrize("reply,expected", [
    ("설명\n<<<DRAFT\n# 제목\n본문\nDRAFT>>>\n후기", "# 제목\n본문"),
    ("<<<DRAFT\r\n한글\r\nDRAFT>>>\r\n", "한글"),
    ("```markdown\n긴 코드블록입니다\n```\n<<<DRAFT\n우선\nDRAFT>>>", "우선"),
    ("```markdown\n짧음\n```\n```markdown\n# 더 긴 초안\n본문입니다\n```", "# 더 긴 초안\n본문입니다"),
    ("응답만 있습니다", None),
    ("<<<DRAFT\n닫히지 않음", None),
    ("<<<DRAFT\n \nDRAFT>>>", None),
    ("```python\n본문\n```", None),
])
def test_extract_draft(reply, expected):
    from frame.core.pipeline import extract_draft
    assert extract_draft(reply) == expected


@pytest.mark.parametrize("separator", ["---", "## 점검표 대조 결과", "### 점검표 대조 결과"])
def test_self_evaluation_is_not_a_source(separator):
    from frame.core.checks import run_checks
    from frame.core.models import DraftSpec
    text = ("# 제목\n본문\n## 출처\n- 실제: https://example.com/source\n"
            f"{separator}\n- 점검 링크: https://example.com/check\n- URL 없는 평가")
    assert run_checks(text, DraftSpec(0, 1000, 0, 1, 0, "경험"), []).metrics["sources"] == 1
    parsed = parse_draft(text)
    assert len(parsed.sources) == 1
    assert parsed.sources[0].url == "https://example.com/source"


def test_missing_reply_does_not_reuse_existing_draft(tmp_path):
    path = tmp_path / "초안.md"
    path.write_text("기존 초안 보존", encoding="utf-8")
    assert main(["write", str(tmp_path), "--topic", "보습", "--draft", "초안.md"],
                writer=FileWriter([None]), fetcher=FakeFetcher(), judge=FakeJudge(),
                config_dir=ROOT / "config") == 1
    assert path.read_text(encoding="utf-8") == "기존 초안 보존"
    assert "기계 점검 실패, 라운드 0" in (tmp_path / "STATE.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("engine", ["claude", "codex"])
def test_resume_keeps_edit_mode(monkeypatch, tmp_path, engine):
    from frame import cli
    prompts = []
    def make_writer(*, allow_edits):
        assert allow_edits is True
        return SimpleNamespace(write=lambda prompt, workdir: prompts.append(prompt))
    monkeypatch.setattr(cli, "select_engine", lambda value: engine)
    monkeypatch.setattr(cli, "ClaudeCliWriter" if engine == "claude" else "CodexCliWriter", make_writer)
    assert main(["write", str(tmp_path)]) == 0
    assert prompts == ["STATE.md 보고 지금 하는 일을 이어서 해줘."]
