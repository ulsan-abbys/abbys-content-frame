"""공유 저장소로 바꾸려면 GateLog의 append/read를 구현해 교체하세요."""

from dataclasses import asdict
import json
from pathlib import Path

from frame.core.models import Decision, GateDecision


class JsonlGateLog:
    def __init__(self, path: str = "logs/gates.jsonl") -> None:
        self.path = Path(path)

    def append(self, d: GateDecision) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(asdict(d), ensure_ascii=False) + "\n")

    def read(self) -> list[GateDecision]:
        if not self.path.exists():
            return []
        decisions = []
        for number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                data["decision"] = Decision(data["decision"])
                if not isinstance(data["missed_by_machine"], bool):
                    raise ValueError("기계 누락 여부는 참 또는 거짓이어야 합니다.")
                decisions.append(GateDecision(**data))
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"관문 로그 {number}번째 줄을 읽을 수 없습니다.") from exc
        return decisions
