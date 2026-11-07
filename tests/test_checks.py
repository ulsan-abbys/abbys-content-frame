from pathlib import Path

import pytest

from frame.config_loader import load_pack, load_profile
from frame.core.checks import (check_duration, count_chars, count_headings,
                               count_human_slots, count_sources, find_violations,
                               run_checks, split_body)
from frame.core.models import DraftSpec, Rule, RulePack

ROOT = Path(__file__).resolve().parents[1]


def test_good_fixture():
    spec, _, names, _ = load_profile(ROOT / "config/profile.example.toml")
    result = run_checks((ROOT / "tests/fixtures/good.md").read_text(encoding="utf-8"), spec,
                        [load_pack(name, ROOT / "config/rules") for name in names])
    assert result.passed, result
    assert result.metrics["headings"] == 3
    assert result.metrics["sources"] == 2
    assert result.metrics["human_slots"] == 2


def test_bad_fixture_reports_metrics_and_medical_lines():
    spec, _, _, _ = load_profile(ROOT / "config/profile.example.toml")
    result = run_checks((ROOT / "tests/fixtures/bad.md").read_text(encoding="utf-8"), spec,
                        [load_pack("medical_ko", ROOT / "config/rules")])
    assert not result.passed
    assert {"metric.chars", "metric.headings", "metric.sources", "metric.human_slots"} <= {f.rule_id for f in result.findings}
    assert any(f.line == 2 and f.severity == "error" for f in result.findings)
    assert any(f.line == 3 and f.severity == "error" for f in result.findings)


def test_body_boundary_and_counts():
    body, sources = split_body("## 제목\r\n가 나\t다\n## 출처 \r\nhttps://a https://b\nhttp://c")
    assert count_chars(body) == 7
    assert count_headings(body) == 1
    assert count_sources(sources) == 2
    assert split_body("## 출처가 아님\n본문") == ("## 출처가 아님\n본문", "")
    assert count_human_slots("[원장 경험] [내 경험]", r"\[(원장|내) 경험") == 2


def test_sources_do_not_inflate_body_metrics():
    result = run_checks("## 가\n## 출처\nhttps://a [내 경험]", DraftSpec(3, 3, 1, 1, 1, r"\[내 경험"), [])
    assert result.metrics == {"chars": 3, "headings": 1, "sources": 1, "human_slots": 0}
    assert not result.passed


def test_warnings_do_not_fail_and_repeated_matches_have_lines():
    pack = RulePack("예제", [Rule("example", "표현", "warn", "확인하세요", "내부 기준")])
    text = "표현\n\n표현 표현"
    assert [f.line for f in find_violations(text, [pack])] == [1, 3, 3]
    assert run_checks(text, DraftSpec(1, 20, 0, 0, 0, "경험"), [pack]).passed


@pytest.mark.parametrize("seconds,valid", [(39, False), (40, True), (45, True), (50, True), (51, False)])
def test_duration(seconds, valid):
    assert (check_duration(seconds, 45, 5) is None) == valid


def test_appendix_after_sources_is_not_scanned_for_violations():
    # 글 끝 "의료법 점검표 대조"는 금칙어를 인용하므로 검사 대상이 아니다 (2026-11-07 시연에서 발견한 거짓 양성)
    from frame.core.checks import split_body

    text = "# 제목\n\n## 하나\n본문\n\n## 출처\n- https://example.com\n\n## 의료법 점검표 대조\n- 완치·100%·최고 표현 없음: 통과\n"
    body, _ = split_body(text)
    assert "완치" not in body
