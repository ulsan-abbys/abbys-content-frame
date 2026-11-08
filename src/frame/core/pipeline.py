"""주입된 포트로 초안 작성과 두 기계 점검을 반복합니다."""

from dataclasses import dataclass, field
import re
from typing import Callable


@dataclass
class WritingProfile:
    genre: str = "생활 정보"
    checklist: str = "AGENTS.md의 점검표"
    experience_label: str = "내 경험"
    persona: dict = field(default_factory=dict)
    style: dict = field(default_factory=dict)

    def guidance(self) -> str:
        labels = {"name": "화자", "field": "분야", "region": "지역", "purpose": "목적"}
        lines = [f"{label}: {self.persona.get(key, '')}" for key, label in labels.items()]
        lines.append(f"말투: {self.style.get('tone', '존댓말, 쉬운 설명')}")
        lines.append("이모지 사용 금지" if self.style.get("forbid_emoji", True) else "이모지 사용 허용")
        return "\n".join(lines)


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


def extract_draft(reply: str) -> str | None:
    """응답의 초안 마커를 우선하고, 없으면 가장 긴 마크다운 블록을 추출합니다."""
    marked = re.search(r"^<<<DRAFT[ \t]*\r?\n(.*?)^DRAFT>>>[ \t]*\r?$",
                       reply, re.MULTILINE | re.DOTALL)
    if marked:
        return marked.group(1).strip() or None
    blocks = re.findall(r"^```markdown[ \t]*\r?\n(.*?)^```[ \t]*\r?$",
                        reply, re.MULTILINE | re.DOTALL)
    return max(blocks, key=len).strip() or None if blocks else None


def run_write_loop(
    topic: str, draft_rel: str, write: Callable[[str], str],
    save_draft: Callable[[str], None],
    check: Callable[[str], tuple[bool, dict, list[str]]],
    score: Callable[[str], tuple[bool, int, int, list[str]]],
    log: Callable[[RoundRecord], None], max_rewrites: int = 2, *,
    clock: Callable[[], float],
    profile: WritingProfile | None = None,
    agents_text: str = "",
    profile_text: str = "",
) -> WriteOutcome:
    if max_rewrites < 0:
        raise ValueError("최대 고쳐 쓰기 횟수는 0 이상이어야 합니다.")
    profile = profile or WritingProfile()
    guidance = profile.guidance()
    context = (
        f"\n작업폴더 AGENTS.md 전문:\n{agents_text}\n"
        f"프로필 지침:\n{profile_text}\n{guidance}\n"
        "파일을 읽거나 쓰지 마세요. 웹 검색과 페이지 열기는 허용합니다. "
        "완성 초안 전문을 <<<DRAFT 줄과 DRAFT>>> 줄 사이에 마크다운으로만 응답하세요. "
        "마커는 각각 독립된 줄에 쓰고 코드 펜스로 감싸지 마세요. "
        "초안 저장과 STATE.md 갱신은 frame이 담당합니다.\n"
    )
    source_rule = (
        "출처는 이 주제를 주된 내용으로 다루는 페이지여야 합니다. 웹에서 검색하고 직접 여세요. "
        "다른 초안의 출처는 이 주제에 관한 경우에만 재사용하고 URL을 지어내지 마세요. PDF가 아닌 웹페이지만 출처로 쓰고, 출처는 `## 출처` 아래 `- 기관명, 페이지 제목: URL` 형식으로 줄마다 하나씩 적으세요. "
        f"[{profile.experience_label}] 슬롯은 비워 두세요."
    )
    prompt = (
        f"주제: {topic}\nAGENTS.md의 끝 기준과 {profile.checklist}를 따라 새 {profile.genre} 초안을 "
        f"작성하세요. 저장 예정 경로: `{draft_rel}`. {source_rule}\n{context}"
    )
    rounds = []
    for index in range(max_rewrites + 1):
        start = clock()
        text = extract_draft(write(prompt))
        if text is None:
            record = RoundRecord(index, False, {}, ["초안 파일이 없습니다."],
                                 False, 0, 0, [], clock() - start)
            rounds.append(record)
            log(record)
            return WriteOutcome(False, rounds, True)
        save_draft(text)
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
            f"아래 점검 결과를 고치도록 초안 전문을 고쳐 쓰세요. 저장 예정 경로: `{draft_rel}`. "
            f"AGENTS.md의 끝 기준과 {profile.checklist}를 따르세요. {source_rule}\n{context}\n"
            + f"현재 초안 전문:\n<<<DRAFT\n{text}\nDRAFT>>>\n점검 결과:\n"
            + (f"현재 측정값: {measured}\n" if measured else "")
            + "\n".join(findings + verdict_lines)
        )
    return WriteOutcome(False, rounds, False)
