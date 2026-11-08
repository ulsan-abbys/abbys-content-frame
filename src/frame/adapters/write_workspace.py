"""초안 경로와 라운드 로그의 파일 입출력을 담당합니다."""

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from frame.core.pipeline import RoundRecord


class WriteWorkspace:
    def __init__(self, workdir: str, topic: str, draft_rel: str | None) -> None:
        self.root = Path(workdir).resolve()
        self.topic = topic
        if draft_rel is None:
            numbers = [int(match.group(1)) for path in (self.root / "초안").glob("*")
                       if path.is_file() and (match := re.match(r"(\d{2,})_", path.name))]
            slug = re.sub(r"\s+", "-", topic)
            slug = "".join(char for char in slug if char.isalnum() or char == "-")
            draft_rel = f"초안/{max(numbers, default=0) + 1:02d}_{slug or '주제'}.md"
        relative = Path(draft_rel)
        self.path = (self.root / relative).resolve()
        if relative.is_absolute() or not self.path.is_relative_to(self.root) or self.path == self.root:
            raise ValueError("초안 경로는 작업 폴더 안의 상대 파일 경로여야 합니다.")
        self.draft_rel = relative.as_posix()

    def read_draft(self) -> str | None:
        try:
            return self.path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            return None

    def log(self, record: RoundRecord) -> None:
        path = self.root / "logs/write_runs.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"topic": self.topic, "draft": self.draft_rel,
                 "timestamp": datetime.now(timezone.utc).isoformat(), **asdict(record)}
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def save_reply(self, reply: str) -> str:
        """Keep each LLM reply next to the round log so a failed round can be diagnosed."""
        path = self.root / "logs/write_replies.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"===== {datetime.now(timezone.utc).isoformat()} {self.draft_rel}\n{reply}\n")
        return reply
