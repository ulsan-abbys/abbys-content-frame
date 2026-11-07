"""다른 AI로 바꾸려면 LLMWriter.write를 구현하고 CLI에 주입하세요."""

import shutil
import subprocess


class ClaudeCliWriter:
    def __init__(self, model: str = "sonnet") -> None:
        self.model = model

    def write(self, prompt: str, workdir: str) -> str:
        # npm installs claude.cmd on Windows, which subprocess cannot find by bare name.
        executable = shutil.which("claude") or "claude"
        try:
            result = subprocess.run(
                [executable, "-p", prompt, "--model", self.model,
                 "--permission-mode", "acceptEdits"],
                cwd=workdir, capture_output=True, text=True, encoding="utf-8",
            )
        except OSError as exc:
            raise RuntimeError("Claude CLI를 실행할 수 없습니다. 설치와 작업 폴더를 확인하세요.") from exc
        if result.returncode:
            raise RuntimeError(f"Claude CLI 실행에 실패했습니다: {result.stderr.strip()}")
        return result.stdout
