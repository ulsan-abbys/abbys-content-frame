"""다른 AI로 바꾸려면 LLMWriter.write를 구현하고 CLI에 주입하세요."""

import shutil
import subprocess


class ClaudeCliWriter:
    def __init__(self, model: str = "sonnet",
                 allowed_tools: tuple[str, ...] = ("WebSearch", "WebFetch"), *,
                 allow_edits: bool = False) -> None:
        self.model = model
        self.allowed_tools = allowed_tools
        self.allow_edits = allow_edits

    def write(self, prompt: str, workdir: str) -> str:
        # npm installs claude.cmd on Windows, which subprocess cannot find by bare name.
        executable = shutil.which("claude") or "claude"
        try:
            # Send the prompt on stdin: claude.cmd (npm) cuts arguments at the first newline.
            result = subprocess.run(
                [executable, "-p", "--model", self.model,
                 *(["--permission-mode", "acceptEdits"] if self.allow_edits else []),
                 "--allowedTools", *self.allowed_tools],
                input=prompt, cwd=workdir, capture_output=True, text=True, encoding="utf-8",
            )
        except OSError as exc:
            raise RuntimeError("Claude CLI를 실행할 수 없습니다. 설치와 작업 폴더를 확인하세요.") from exc
        if result.returncode:
            raise RuntimeError(f"Claude CLI 실행에 실패했습니다: {result.stderr.strip()}")
        return result.stdout
