"""주입된 포트로 초안 작성과 두 기계 점검을 반복합니다."""

from dataclasses import dataclass
from typing import Callable


@dataclass
class RoundRecord:
    round: int
    check_passed: bool
    metrics: dict
    findings: list[str]
    score_passed: bool
    supported: int
    required: int
    verdict_lines: list[str]
    seconds: float


@dataclass
class WriteOutcome:
    passed: bool
    rounds: list[RoundRecord]
    draft_missing: bool


def run_write_loop(
    topic: str, draft_rel: str, write: Callable[[str], object],
    read_draft: Callable[[], str | None],
    check: Callable[[str], tuple[bool, dict, list[str]]],
    score: Callable[[str], tuple[bool, int, int, list[str]]],
    log: Callable[[RoundRecord], None], max_rewrites: int = 2, *,
    clock: Callable[[], float],
) -> WriteOutcome:
    if max_rewrites < 0:
        raise ValueError("최대 고쳐 쓰기 횟수는 0 이상이어야 합니다.")
    source_rule = (
        "출처는 이 주제를 주된 내용으로 다루는 페이지여야 합니다. 웹에서 검색하고 직접 여세요. "
        "다른 초안의 출처는 이 주제에 관한 경우에만 재사용하고 URL을 지어내지 마세요. "
        "[원장 경험] 슬롯은 비워 두세요."
    )
    prompt = (
        f"주제: {topic}\nAGENTS.md의 끝 기준과 의료법 점검표를 따라 새 건강정보 초안을 "
        f"정확히 `{draft_rel}`에 작성하세요. {source_rule}\nSTATE.md를 갱신하세요."
    )
    rounds = []
    for index in range(max_rewrites + 1):
        start = clock()
        write(prompt)
        text = read_draft()
        if text is None:
            record = RoundRecord(index, False, {}, ["초안 파일이 없습니다."],
                                 False, 0, 0, [], clock() - start)
            rounds.append(record)
            log(record)
            return WriteOutcome(False, rounds, True)
        check_passed, metrics, findings = check(text)
        score_passed, supported, required, verdict_lines = score(text)
        record = RoundRecord(index, check_passed, metrics, findings, score_passed,
                             supported, required, verdict_lines, clock() - start)
        rounds.append(record)
        log(record)
        if check_passed and score_passed:
            return WriteOutcome(True, rounds, False)
        measured = ", ".join(f"{key}={value}" for key, value in metrics.items())
        prompt = (
            f"아래 점검 결과를 고치도록 `{draft_rel}`만 고쳐 쓰세요. "
            f"AGENTS.md의 끝 기준과 의료법 점검표를 따르세요. {source_rule}\n"
            + (f"현재 측정값: {measured}\n" if measured else "")
            + "\n".join(findings + verdict_lines)
        )
    return WriteOutcome(False, rounds, False)
