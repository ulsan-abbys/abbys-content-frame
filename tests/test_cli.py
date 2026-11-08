from pathlib import Path

import pytest

from frame.adapters.mpt_cli import MoneyPrinterTurboRenderer
from frame.cli import main

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"


@pytest.mark.parametrize("name,code", [("good", 0), ("bad", 1)])
def test_check_exit_codes(name, code, capsys):
    assert main(["check", str(ROOT / f"tests/fixtures/{name}.md")], config_dir=CONFIG) == code
    assert "본문 글자 수" in capsys.readouterr().out


def test_gate_record_status(tmp_path, capsys):
    log = str(tmp_path / "nested/gates.jsonl")
    assert main(["gate", "record", "--gate", "G2", "--decision", "approved", "--run-id", "시연",
                 "--note", "사실 확인 완료", "--log", log], config_dir=CONFIG) == 0
    assert main(["gate", "--log", log, "status"], config_dir=CONFIG) == 0
    output = capsys.readouterr().out
    assert "G2" in output and "승인 1" in output and "사람 검토 필요" in output
    assert "사실 확인 완료" in Path(log).read_text(encoding="utf-8")


def test_invalid_gate_does_not_write(tmp_path):
    log = tmp_path / "gates.jsonl"
    assert main(["gate", "record", "--gate", "G99", "--decision", "approved", "--log", str(log)], config_dir=CONFIG) == 1
    assert not log.exists()


def test_graph_prints_human(capsys):
    assert main(["graph"], config_dir=CONFIG) == 0
    assert "G3 게시 클릭: 항상 사람" in capsys.readouterr().out


def test_write_with_fake(capsys):
    class FakeWriter:
        def write(self, prompt, workdir):
            assert prompt == "STATE.md 보고 지금 하는 일을 이어서 해줘."
            assert workdir == "작업폴더"
            return "가짜 초안"
    assert main(["write", "작업폴더"], writer=FakeWriter()) == 0
    assert "가짜 초안" in capsys.readouterr().out


def test_render_with_fake(tmp_path, capsys):
    class FakeRenderer:
        def render(self, script, out_dir):
            assert script == "대본입니다."
            assert out_dir == str(tmp_path)
            return str(tmp_path / "영상.mp4")
    script = tmp_path / "대본.txt"
    script.write_text("대본입니다.", encoding="utf-8")
    assert main(["render", str(script), "--out", str(tmp_path)], renderer=FakeRenderer()) == 0
    assert "영상 생성 완료" in capsys.readouterr().out
    assert MoneyPrinterTurboRenderer(mpt_dir=str(tmp_path)).voice == "ko-KR-SunHiNeural-Female"


def test_missing_file_and_corrupt_log_are_reported(tmp_path, capsys):
    assert main(["check", str(tmp_path / "missing.md")], config_dir=CONFIG) == 1
    log = tmp_path / "gates.jsonl"
    log.write_text("잘못된 로그\n", encoding="utf-8")
    assert main(["gate", "status", "--log", str(log)], config_dir=CONFIG) == 1
    assert "관문 로그 1번째 줄" in capsys.readouterr().out


@pytest.mark.parametrize("verdict,code", [("supports", 0), ("unrelated", 1)])
@pytest.mark.parametrize("profile_mode", ["fallback", "default", "explicit"])
def test_score_with_fakes(tmp_path, capsys, verdict, code, profile_mode):
    config = tmp_path / "config"
    config.mkdir()
    profile = (CONFIG / "profile.example.toml").read_text(encoding="utf-8")
    (config / "profile.example.toml").write_text(profile, encoding="utf-8")
    # 기본 프로필과 명시 프로필은 서로 다른 최소 출처 수를 사용합니다.
    custom = config / "profile.toml"
    required = 2 if profile_mode == "fallback" else 1
    if profile_mode != "fallback":
        custom.write_text(profile.replace("min_sources = 2", "min_sources = 1"), encoding="utf-8")
    if profile_mode == "explicit":
        custom = config / "custom.toml"
        custom.write_text(profile.replace("min_sources = 2", "min_sources = 3"), encoding="utf-8")
        required = 3
        code = 1
    draft = tmp_path / "초안.md"
    draft.write_text("# 보습\n본문\n## 출처\n- 안내: https://example.com/a\n"
                     "- 연구: https://example.com/b\n- [확인 필요]\n", encoding="utf-8-sig")

    class FakeFetcher:
        def fetch(self, url):
            return "보습은 건조한 피부의 수분 유지에 도움이 됩니다."

    class FakeJudge:
        def judge(self, title, body, label, page_text):
            assert title == "보습" and "## 출처" not in body
            return {"verdict": verdict, "evidence": page_text, "reason": "주제 판정"}

    args = ["score", str(draft)]
    if profile_mode == "explicit":
        args += ["--profile", str(custom)]
    assert main(args, fetcher=FakeFetcher(), judge=FakeJudge(), config_dir=config) == code
    output = capsys.readouterr().out
    assert f"[{verdict}] 안내 - 주제 판정" in output
    assert "근거: 보습은 건조한 피부의 수분 유지에 도움이 됩니다." in output
    assert "[unopened] [확인 필요] - URL 없음" in output
    assert f"출처 대응 {2 if verdict == 'supports' else 0}/{required}" in output
    assert ("채점 통과" if code == 0 else "채점 실패") in output


def test_score_error_exit_code(tmp_path, capsys):
    assert main(["score", str(tmp_path / "missing.md")], config_dir=CONFIG) == 2
    assert "오류: 작업을 완료할 수 없습니다." in capsys.readouterr().out


def test_score_judge_error_exit_code(tmp_path, capsys):
    draft = tmp_path / "초안.md"
    draft.write_text("# 제목\n## 출처\n- 출처: https://example.com\n", encoding="utf-8")

    class FakeFetcher:
        def fetch(self, url):
            return "페이지 본문"

    class FailingJudge:
        def judge(self, *args):
            raise RuntimeError("판정기 실행 실패")

    assert main(["score", str(draft)], config_dir=CONFIG,
                fetcher=FakeFetcher(), judge=FailingJudge()) == 2
    assert "오류: 작업을 완료할 수 없습니다." in capsys.readouterr().out
