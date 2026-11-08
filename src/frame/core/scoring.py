"""초안의 출처와 본문 주제 대응을 판정하는 순수 도메인."""

from dataclasses import dataclass
import re
from typing import Callable, Literal

from frame.core.checks import split_body


@dataclass(frozen=True)
class DraftSource:
    label: str
    url: str | None


@dataclass(frozen=True)
class ParsedDraft:
    title: str
    body: str
    sources: list[DraftSource]


@dataclass(frozen=True)
class SourceVerdict:
    url: str | None
    label: str
    opened: bool
    verdict: Literal["supports", "partial", "unrelated", "unopened"]
    evidence: str
    reason: str


@dataclass(frozen=True)
class ScoreResult:
    passed: bool
    verdicts: list[SourceVerdict]
    supported: int
    required: int


def parse_draft(text: str) -> ParsedDraft:
    title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), "")
    body, section = split_body(text)
    sources = []
    for line in section.splitlines():
        line = line.strip()
        if line == "---" or line.startswith("## "):
            break
        if not line.startswith("- "):
            continue
        item = line[2:].strip()
        match = re.search(r"https?://[^\s<>\]\)]+", item)
        label = (item[:match.start()] if match else item).strip().rstrip(":").strip()
        sources.append(DraftSource(label, match.group() if match else None))
    return ParsedDraft(title, body, sources)


def score_sources(parsed: ParsedDraft, fetch: Callable[[str], str | None],
                  judge: Callable[[str, str, str, str], dict], min_sources: int) -> ScoreResult:
    verdicts = []
    for source in parsed.sources:
        page = fetch(source.url) if source.url is not None else None
        if page is None:
            reason = "URL 없음" if source.url is None else "페이지를 열지 못함"
            verdicts.append(SourceVerdict(source.url, source.label, False, "unopened", "", reason))
            continue
        decision = judge(parsed.title, parsed.body, source.label, page)
        verdict = decision.get("verdict", "unrelated")
        evidence = decision.get("evidence", "")
        reason = decision.get("reason", "")
        if (verdict not in ("supports", "partial", "unrelated")
                or not isinstance(evidence, str) or not isinstance(reason, str)):
            verdict, evidence, reason = "unrelated", "", "판정 응답을 읽지 못함"
        normalized_page = "".join(char for char in page if char.isalnum())
        sentences = ["".join(char for char in sentence if char.isalnum())
                     for sentence in re.split(r"[.!?。\r\n]+", evidence)]
        if verdict in ("supports", "partial") and not any(
                len(sentence) >= 15 and sentence in normalized_page for sentence in sentences):
            verdict, reason = "unrelated", "근거 문장이 페이지에 없음"
        verdicts.append(SourceVerdict(source.url, source.label, True, verdict, evidence, reason))
    supported = sum(v.verdict == "supports" for v in verdicts)
    passed = not any(v.verdict == "unrelated" for v in verdicts) and supported >= min_sources
    return ScoreResult(passed, verdicts, supported, min_sources)
