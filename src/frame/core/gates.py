"""검수 이력이 쌓이면 점진적으로 자동화하되 기계 누락 시 되돌린다."""

from frame.core.models import Decision, GateDecision, GateLevel, GateSpec


def next_level(history: list[GateDecision], spec: GateSpec, current: GateLevel,
               window: int = 10, threshold: int = 9) -> GateLevel:
    if spec.start == GateLevel.HUMAN_ONLY or spec.max == GateLevel.HUMAN_ONLY or current == GateLevel.HUMAN_ONLY:
        return GateLevel.HUMAN_ONLY
    if not 1 <= threshold <= window:
        raise ValueError("승급 기준은 1 이상이며 검토 구간 크기 이하여야 합니다.")
    relevant = [d for d in history if d.gate == spec.id]
    if relevant and relevant[-1].missed_by_machine:
        return GateLevel.L0
    last_miss = max((i for i, d in enumerate(relevant) if d.missed_by_machine), default=-1)
    recent = relevant[last_miss + 1:][-window:]
    if (len(recent) == window
            and not any(d.missed_by_machine for d in recent)
            and sum(d.decision == Decision.APPROVED for d in recent) >= threshold):
        levels = [GateLevel.L0, GateLevel.L1, GateLevel.L2]
        return levels[min(levels.index(current) + 1, levels.index(spec.max))]
    return current


def needs_human_review(level: GateLevel, run_index: int) -> bool:
    if level in (GateLevel.L0, GateLevel.HUMAN_ONLY):
        return True
    return level == GateLevel.L1 and run_index % 3 == 0


def replay(history: list[GateDecision], spec: GateSpec) -> GateLevel:
    current = spec.start
    considered: list[GateDecision] = []
    for decision in sorted((d for d in history if d.gate == spec.id), key=lambda d: d.ts):
        considered.append(decision)
        current = next_level(considered, spec, current)
    return current
