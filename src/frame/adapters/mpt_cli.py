"""다른 영상 도구는 VideoRenderer.render를 구현해 교체하세요. MPT_DIR로 설치 폴더를 지정합니다."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def last_json_object(stdout: str) -> dict:
    decoder = json.JSONDecoder()
    objects = []
    index = 0
    while index < len(stdout):
        start = stdout.find("{", index)
        if start < 0:
            break
        try:
            value, length = decoder.raw_decode(stdout[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(value, dict):
            objects.append(value)
        index = start + length
    if not objects:
        raise RuntimeError("영상 도구 출력에서 JSON 결과를 찾지 못했습니다.")
    return objects[-1]


class MoneyPrinterTurboRenderer:
    def __init__(self, mpt_dir: str | None = None, materials: str = "materials",
                 voice: str = "ko-KR-SunHiNeural-Female", font: str = "malgunbd.ttf") -> None:
        self.mpt_dir = mpt_dir or os.environ.get("MPT_DIR")
        self.materials = materials
        self.voice = voice
        self.font = font

    def render(self, script: str, out_dir: str) -> str:
        if not self.mpt_dir:
            raise RuntimeError("MPT_DIR 환경 변수에 MoneyPrinterTurbo 설치 폴더를 지정하세요.")
        root = Path(self.mpt_dir).resolve()
        python = root / (".venv/Scripts/python.exe" if sys.platform == "win32" else ".venv/bin/python")
        subject = next((line.strip() for line in script.splitlines() if line.strip()), "지역 건강 정보")
        args = [str(python), "cli.py", "--video-subject", subject,
                "--video-script", script, "--video-language", "ko-KR",
                "--video-source", "local", "--video-materials", self.materials,
                "--video-aspect", "9:16", "--voice-name", self.voice,
                "--bgm-type", "none", "--font-name", self.font,
                "--subtitle-position", "bottom", "--text-fore-color", "#1B2430",
                "--stroke-color", "#FFFFFF", "--stroke-width", "2"]
        try:
            result = subprocess.run(args, cwd=root, capture_output=True, text=True,
                                    encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        except OSError as exc:
            raise RuntimeError("영상 도구를 실행할 수 없습니다. 설치 폴더를 확인하세요.") from exc
        if result.returncode:
            raise RuntimeError(f"영상 렌더링에 실패했습니다: {result.stderr.strip()}")
        try:
            video = last_json_object(result.stdout)["result"]["videos"][0]
            if not isinstance(video, str) or not video:
                raise ValueError("영상 경로가 비어 있습니다.")
            source = Path(video)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("영상 결과에 result.videos[0] 경로가 없습니다.") from exc
        if not source.is_absolute():
            source = root / source
        destination = Path(out_dir).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / source.name
        if source.resolve() != target:
            shutil.copy2(source, target)
        elif not source.is_file():
            raise RuntimeError("영상 도구가 반환한 파일을 찾을 수 없습니다.")
        return str(target)
