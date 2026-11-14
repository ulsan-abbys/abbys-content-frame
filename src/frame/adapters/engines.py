"""PATH와 명시 설정으로 외부 CLI 엔진을 선택합니다."""

import os
import shutil


class EngineUnavailable(RuntimeError):
    pass


def select_engine(requested: str | None = None) -> str:
    engine = requested if requested is not None else os.environ.get("FRAME_ENGINE", "auto")
    if engine not in ("auto", "claude", "codex"):
        raise EngineUnavailable("FRAME_ENGINE은 auto, claude, codex 중 하나여야 합니다.")
    candidates = ("codex", "claude") if engine == "auto" else (engine,)
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    raise EngineUnavailable("Claude Code 또는 Codex CLI 중 하나를 설치하고 로그인하세요")
