import pytest

from frame.core.scoring import parse_draft, score_sources


DRAFT = """# 보습 관리
보습을 꾸준히 합니다.
## 출처
- 안내: https://example.com/one
- 연구: https://example.com/two
- [확인 필요]
---
## 점검표
- 제외: https://example.com/check
"""


def test_parse_draft():
    parsed = parse_draft(DRAFT)
    assert parsed.title == "보습 관리"
    assert parsed.body == "# 보습 관리\n보습을 꾸준히 합니다.\n"
    assert [(s.label, s.url) for s in parsed.sources] == [
        ("안내", "https://example.com/one"), ("연구", "https://example.com/two"),
        ("[확인 필요]", None),
    ]


def test_parse_heading_boundary_and_missing_section():
    assert len(parse_draft(DRAFT.replace("---", "## 부록")).sources) == 3
    parsed = parse_draft("본문만 있음")
    assert (parsed.title, parsed.body, parsed.sources) == ("", "본문만 있음", [])
    assert len(parse_draft(DRAFT.replace("\n", "\r\n")).sources) == 3


@pytest.mark.parametrize("verdict,evidence,passed,supported", [
    ("supports", "보습은 건조한 피부의 수분 유지에 도움이 됩니다.", True, 2),
    ("unrelated", "보습은 건조한 피부의 수분 유지에 도움이 됩니다.", False, 0),
    ("partial", "보습은 건조한 피부의 수분 유지에 도움이 됩니다.", False, 0),
    ("supports", "페이지에 없는 문장", False, 0),
    ("partial", "페이지에 없는 문장", False, 0),
    ("supports", "   ", False, 0),
])
def test_scoring(verdict, evidence, passed, supported):
    def fetch(url):
        assert url.startswith("https://example.com/")
        return "보습은\n  건조한 피부의 수분 유지에 도움이 됩니다."

    def judge(title, body, label, page):
        assert title == "보습 관리" and "## 출처" not in body
        assert label in ("안내", "연구")
        return {"verdict": verdict, "evidence": evidence, "reason": "판정 이유"}

    result = score_sources(parse_draft(DRAFT), fetch, judge, 2)
    assert (result.passed, result.supported, result.required) == (passed, supported, 2)
    assert result.verdicts[-1].reason == "URL 없음"
    assert result.verdicts[-1].verdict == "unopened"
    assert not result.verdicts[-1].opened
    if verdict in ("supports", "partial") and evidence.strip() != "보습은 건조한 피부의 수분 유지에 도움이 됩니다.":
        assert result.verdicts[0].verdict == "unrelated"
        assert result.verdicts[0].reason == "근거 문장이 페이지에 없음"


def test_unopened_is_not_judged_or_counted():
    def judge(*args):
        pytest.fail("열지 못한 출처는 판정하면 안 됩니다.")

    result = score_sources(parse_draft(DRAFT), lambda url: None, judge, 2)
    assert not result.passed and result.supported == 0
    assert all(v.verdict == "unopened" and not v.opened for v in result.verdicts)


def test_unrelated_fails_even_with_enough_supports():
    draft = DRAFT.replace("- [확인 필요]", "- 무관: https://example.com/other")
    result = score_sources(parse_draft(draft), lambda url: "보습은 건조한 피부의 수분 유지에 도움이 됩니다.", lambda t, b, label, p: {
        "verdict": "unrelated" if label == "무관" else "supports",
        "evidence": "보습은 건조한 피부의 수분 유지에 도움이 됩니다.", "reason": "판정 이유",
    }, 2)
    assert result.supported == 2 and not result.passed
