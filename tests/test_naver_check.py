"""네이버 캡처 판정과 CLI의 오프라인 회귀 검사."""

import json
import re
from urllib.parse import quote

import pytest

from frame.cli import main
from frame.core.naver_capture import CAPTURE_SCRIPT
from frame.core.naver_check import check_naver, extract_expected, normalize_href


MARKDOWN = """# 점검 제목

## 첫 소제목

첫 문단의 **중요한 말**과 [출처](https://Example.com/page/).

- 항목 하나
- 항목 둘

## 둘째 소제목

[내 경험: 직접 작성]
"""


def make_capture(markdown=MARKDOWN, label="내 경험"):
    expected = extract_expected(markdown, label)
    return dict(title=expected.title, blocks=[dict(
        tag="h2" if text in expected.headings else "li" if text in expected.items else "p",
        cls="", text=text, fontSize=24 if text in expected.headings else 16,
        fontWeight=700 if text in expected.headings else 400,
        inList=text in expected.items, bulletPrefix=False) for text in expected.body],
        bolds=expected.bolds[:], links=[dict(text=t, href=h) for t, h in expected.links],
        meta=dict(schema=1))


def statuses(result, code):
    return [item["status"] for item in result["items"] if item["code"] == code]


def test_complete_capture_warns_only_for_unfilled_experience():
    result = check_naver(MARKDOWN, make_capture())
    assert result["verdict"] == "WARN"
    assert statuses(result, "C8") == ["WARN"]
    assert all(i["status"] == "PASS" for i in result["items"] if i["code"] != "C8")
    assert result["counts"] == {"headings": {"matched": 2, "total": 2},
                                "items": {"matched": 2, "total": 2},
                                "bolds": {"matched": 2, "total": 2},
                                "links": {"matched": 1, "total": 1}}


def test_complete_without_slots_passes():
    md = MARKDOWN.replace("[내 경험: 직접 작성]", "직접 쓴 경험입니다.")
    assert check_naver(md, make_capture(md))["verdict"] == "PASS"


@pytest.mark.parametrize("weight,status", [(700, "WARN"), (400, "FAIL")])
def test_heading_loses_structure(weight, status):
    capture = make_capture()
    capture["blocks"][0].update(tag="p", fontSize=16, fontWeight=weight)
    assert statuses(check_naver(MARKDOWN, capture), "C2")[0] == status


@pytest.mark.parametrize("change", [dict(cls="sectionTitle"), dict(fontSize=19)])
def test_heading_class_or_size_preserved(change):
    capture = make_capture()
    capture["blocks"][0].update(tag="p", fontSize=16, fontWeight=400)
    capture["blocks"][0].update(change)
    assert statuses(check_naver(MARKDOWN, capture), "C2")[0] == "PASS"


def test_heading_order():
    capture = make_capture()
    capture["blocks"][0], capture["blocks"][4] = capture["blocks"][4], capture["blocks"][0]
    assert statuses(check_naver(MARKDOWN, capture), "C2_ORDER") == ["FAIL"]


@pytest.mark.parametrize("prefix", ["", "• ", "1. ", "- ", "* ", "· "])
def test_list_markers(prefix):
    capture = make_capture()
    capture["blocks"][2].update(inList=False, bulletPrefix=bool(prefix), text=prefix + "항목 하나")
    result = check_naver(MARKDOWN, capture)
    assert statuses(result, "C3")[0] == ("PASS" if prefix else "FAIL")
    assert statuses(result, "C6") == ["PASS"]


def test_missing_link_and_changed_caption():
    capture = make_capture()
    capture["links"][0]["text"] = "다른 이름"
    assert statuses(check_naver(MARKDOWN, capture), "C5") == ["WARN"]
    capture["links"] = []
    assert statuses(check_naver(MARKDOWN, capture), "C5") == ["FAIL"]


@pytest.mark.parametrize("parameter", ["url", "u"])
def test_naver_redirect(parameter):
    capture = make_capture()
    capture["links"][0]["href"] = f"https://link.naver.com/redirect?{parameter}=" + quote("HTTPS://EXAMPLE.COM/page", safe="")
    assert statuses(check_naver(MARKDOWN, capture), "C5") == ["PASS"]
    assert normalize_href("https://evilnaver.com/?url=https%3A%2F%2Fexample.com") != "https://example.com"


@pytest.mark.parametrize("token", ["본문 복사", "제목 복사", "붙여넣기 순서", "확인: 제목", "**", "## 제목", "](http"])
def test_leaks(token):
    capture = make_capture()
    capture["title"] += " " + token
    assert statuses(check_naver(MARKDOWN, capture), "C7") == ["FAIL"]


def test_missing_paragraph_and_bold():
    capture = make_capture()
    capture["blocks"].pop(1)
    capture["bolds"] = []
    result = check_naver(MARKDOWN, capture)
    assert statuses(result, "C4") == ["FAIL", "FAIL"]
    assert statuses(result, "C6") == ["FAIL"]
    assert any("빠진 문단" in i["message"] for i in result["items"])


def test_normalization_and_custom_label():
    md = MARKDOWN.replace("내 경험:", "나의 기록:")
    capture = make_capture(md, "나의 기록")
    capture["title"] = "점검\u200b  제목"
    result = check_naver(md, capture, "나의 기록")
    assert statuses(result, "C1") == ["PASS"]
    assert statuses(result, "C8") == ["WARN"]
    assert extract_expected(md, "나의 기록").slot_count == 1


def test_removed_slot_reports_uncertainty():
    capture = make_capture()
    capture["blocks"][-1]["text"] = "제가 직접 작성했습니다."
    result = check_naver(MARKDOWN, capture)
    assert statuses(result, "C8_INFO") == ["PASS"]


def test_capture_script_is_read_only(capsys):
    for token in ("fetch", "XMLHttpRequest", "sendBeacon", ".click(", "submit", "remove("):
        assert token not in CAPTURE_SCRIPT
    assert not re.search(r"\.(?:innerHTML|value)\s*=", CAPTURE_SCRIPT)
    assert "typeof copy === 'function'" in CAPTURE_SCRIPT
    assert main(["naver", "capture-script"]) == 0
    assert capsys.readouterr().out.strip() == CAPTURE_SCRIPT


@pytest.mark.parametrize("stage,exit_code", [("draft", 0), ("publish", 1)])
@pytest.mark.parametrize("double", [False, True])
def test_cli_bom_double_json_and_publish(tmp_path, capsys, stage, exit_code, double):
    md = tmp_path / "draft.md"
    md.write_text(MARKDOWN, encoding="utf-8")
    capture = tmp_path / "capture.json"
    data = json.dumps(make_capture(), ensure_ascii=False)
    capture.write_text(json.dumps(data) if double else data, encoding="utf-8-sig")
    assert main(["naver", "check", str(md), str(capture), "--stage", stage, "--json"]) == exit_code
    result = json.loads(capsys.readouterr().out)
    assert result["verdict"] == ("WARN" if stage == "draft" else "FAIL")


@pytest.mark.parametrize("data", ["invalid", "[]", "{}", '{"title": 1}', '"invalid"'])
def test_cli_input_errors(tmp_path, capsys, data):
    md = tmp_path / "draft.md"
    md.write_text(MARKDOWN, encoding="utf-8")
    capture = tmp_path / "capture.json"
    capture.write_text(data, encoding="utf-8")
    assert main(["naver", "check", str(md), str(capture)]) == 2
    assert "오류:" in capsys.readouterr().out


def test_cli_human_summary(tmp_path, capsys):
    md = tmp_path / "draft.md"
    md.write_text(MARKDOWN, encoding="utf-8")
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps(make_capture()), encoding="utf-8")
    assert main(["naver", "check", str(md), str(capture), "--label", "내 경험"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "판정: WARN — 소제목 2/2 · 목록 2/2 · 굵게 2/2 · 링크 1/1"
