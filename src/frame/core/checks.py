"""문자열만 받아 결과를 돌려주는 초안·영상 점검."""

import re

from frame.core.models import CheckResult, DraftSpec, Finding, RulePack


def split_body(text: str) -> tuple[str, str]:
    heading = re.search(r"^## 출처[ \t]*\r?$", text, re.MULTILINE)
    if heading is None:
        return text, ""
    return text[:heading.start()], text[heading.end():]


def count_chars(body: str) -> int:
    return sum(not char.isspace() for char in body)


def count_headings(body: str) -> int:
    return sum(line.startswith("## ") for line in body.splitlines())


def count_sources(sources_section: str) -> int:
    return sum(bool(re.search(r"https?://", line)) for line in sources_section.splitlines())


def count_human_slots(text: str, pattern: str) -> int:
    return sum(1 for _ in re.finditer(pattern, text))


def find_violations(text: str, packs: list[RulePack]) -> list[Finding]:
    findings = []
    for pack in packs:
        for rule in pack.rules:
            for match in re.finditer(rule.pattern, text):
                findings.append(Finding(
                    rule.id, rule.severity, f"{rule.reason} (참고: {rule.ref})",
                    text.count("\n", 0, match.start()) + 1,
                ))
    return findings


def run_checks(text: str, spec: DraftSpec, packs: list[RulePack]) -> CheckResult:
    body, sources = split_body(text)
    metrics = {
        "chars": count_chars(body),
        "headings": count_headings(body),
        "sources": count_sources(sources),
        "human_slots": count_human_slots(body, spec.human_slot_pattern),
    }
    findings = find_violations(body, packs)  # 출처 아래(점검표 대조 등)는 금칙어 검사에서 뺀다
    requirements = [
        ("chars", spec.min_chars <= metrics["chars"] <= spec.max_chars,
         f"본문 공백 제외 글자 수는 {spec.min_chars}~{spec.max_chars}자여야 합니다."),
        ("headings", metrics["headings"] == spec.headings,
         f"본문 소제목은 {spec.headings}개여야 합니다."),
        ("sources", metrics["sources"] >= spec.min_sources,
         f"출처 URL이 있는 줄은 {spec.min_sources}개 이상이어야 합니다."),
        ("human_slots", metrics["human_slots"] >= spec.min_human_slots,
         f"본문의 사람 경험 입력 자리는 {spec.min_human_slots}개 이상이어야 합니다."),
    ]
    for key, valid, message in requirements:
        if not valid:
            findings.append(Finding(f"metric.{key}", "error", message, None))
    return CheckResult(not any(f.severity == "error" for f in findings), findings, metrics)


def check_duration(seconds: float, target: float, tolerance: float) -> Finding | None:
    if not target - tolerance <= seconds <= target + tolerance:
        return Finding("metric.duration", "error",
                       f"영상 길이는 {target - tolerance}~{target + tolerance}초여야 합니다.", None)
    return None
