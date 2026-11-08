"""Codex CLI의 표준 입력과 마지막 응답 파일을 사용하는 작성·판정 어댑터."""

from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from frame.adapters.judge_response import judge_prompt, parse_judgment


def _execute(prompt: str, workdir: str, sandbox: str, search: str) -> str:
    executable = shutil.which("codex") or "codex"
    try:
        with TemporaryDirectory() as output_dir:
            output = Path(output_dir) / "last-message.txt"
            result = subprocess.run(
                [executable, "exec", "--skip-git-repo-check", "-s", sandbox,
                 "-C", str(Path(workdir).resolve()), "-c", f"web_search={search}",
                 "--output-last-message", str(output), "-"],
                input=prompt, cwd=workdir, capture_output=True, text=True, encoding="utf-8",
            )
            if result.returncode:
                raise RuntimeError(f"Codex CLI 실행에 실패했습니다: {result.stderr.strip()}")
            if not output.is_file() or not output.read_text(encoding="utf-8").strip():
                raise RuntimeError("Codex CLI의 마지막 응답이 없습니다. 로그인과 실행 결과를 확인하세요.")
            return output.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("Codex CLI를 실행할 수 없습니다. 설치와 작업 폴더를 확인하세요.") from exc


class CodexCliWriter:
    def __init__(self, *, allow_edits: bool = False) -> None:
        self.allow_edits = allow_edits

    def write(self, prompt: str, workdir: str) -> str:
        return _execute(prompt, workdir,
                        "workspace-write" if self.allow_edits else "read-only", "live")


class CodexCliJudge:
    def judge(self, title: str, body: str, label: str, page_text: str) -> dict:
        with TemporaryDirectory() as workdir:
            response = _execute(judge_prompt(title, body, label, page_text),
                                workdir, "read-only", "disabled")
        return parse_judgment(response)
