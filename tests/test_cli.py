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
