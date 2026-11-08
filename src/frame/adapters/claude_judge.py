"""Claude CLI로 출처의 주제 관련성을 판정합니다."""

import shutil
import subprocess
from tempfile import TemporaryDirectory

from frame.adapters.judge_response import judge_prompt, parse_judgment


class ClaudeCliJudge:
    def __init__(self, model: str = "sonnet") -> None:
        self.model = model

    def judge(self, title: str, body: str, label: str, page_text: str) -> dict:
        prompt = judge_prompt(title, body, label, page_text)
        executable = shutil.which("claude") or "claude"
        try:
            with TemporaryDirectory() as workdir:
                result = subprocess.run(
                    [executable, "-p", "--model", self.model, "--output-format", "text"],
                    input=prompt, cwd=workdir, capture_output=True, text=True, encoding="utf-8",
                )
        except OSError as exc:
            raise RuntimeError("Claude CLI를 실행할 수 없습니다. 설치를 확인하세요.") from exc
        if result.returncode:
            raise RuntimeError(f"Claude CLI 실행에 실패했습니다: {result.stderr.strip()}")
        return parse_judgment(result.stdout)
