"""네트워크·실제 브라우저 없이 임시저장 어댑터 경계를 검사한다."""

from contextlib import contextmanager
import builtins
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from frame.adapters.naver_browser import NaverBrowser, guarded_click, is_publish_label, profile_path
from frame.adapters import naver_browser
from frame.core.naver import NaverDraft, NaverLoginRequired, NaverSetupRequired


@pytest.mark.parametrize("label", ["발행", "글 발행", "예약 발행", "저장 후 발행", "발 행", "발\u200b행"])
def test_publish_label_is_blocked(label):
    assert is_publish_label(label)
    locator = Mock()
    locator.evaluate.return_value = label
    with pytest.raises(RuntimeError, match="발행"):
        guarded_click(locator)
    locator.click.assert_not_called()


@pytest.mark.parametrize("label", ["저장", "취소", "도움말 닫기", "제목"])
def test_safe_labels_can_be_clicked(label):
    assert not is_publish_label(label)
    locator = Mock()
    locator.evaluate.return_value = label
    guarded_click(locator)
    locator.click.assert_called_once()


def test_profile_override_and_repository_rejection(tmp_path, monkeypatch):
    profile = tmp_path / "sessions"
    monkeypatch.setenv("ABBYS_NAVER_PROFILE", str(profile))
    assert profile_path() == profile.resolve()
    (tmp_path / ".git").mkdir()
    with pytest.raises(NaverSetupRequired, match="저장소 밖"):
        profile_path()


def test_login_redirect_inside_frame():
    browser = NaverBrowser()
    main = SimpleNamespace(url="https://blog.naver.com/example/postwrite")
    login = SimpleNamespace(url="https://nid.naver.com/nidlogin.login")
    browser.page = SimpleNamespace(url=main.url, main_frame=main, frames=[main, login])
    with pytest.raises(NaverLoginRequired, match="frame naver login"):
        browser._check_login()


def fake_browser(monkeypatch):
    browser = NaverBrowser()
    page = Mock()
    context = Mock()
    page.url = "https://blog.naver.com/example/postwrite"
    page.frames = []
    page.locator.return_value.count.return_value = 0
    page.get_by_text.return_value.count.return_value = 0
    context.cookies.return_value = [{"name": "NID_AUT"}]
    browser.page = page

    @contextmanager
    def session():
        yield context, page

    monkeypatch.setattr(browser, "_browser", session)
    monkeypatch.setattr(browser, "_step", lambda *args: None)
    monkeypatch.setattr(browser, "_dismiss", lambda: None)
    return browser, context, page


def test_save_clipboard_failure_uses_plain_text_and_only_save(monkeypatch):
    browser, context, page = fake_browser(monkeypatch)
    title, body, save = Mock(), Mock(), Mock()
    title.evaluate.return_value = "제목"
    # 클릭 가드, 클립보드 실패 후 본문 글자 수.
    body.evaluate.side_effect = ["", "", "내용"]
    save.evaluate.return_value = "저장"
    context.grant_permissions.side_effect = RuntimeError("클립보드 불가")
    monkeypatch.setattr(browser, "_find", Mock(side_effect=[title, body, save]))
    draft = NaverDraft("제목", "<p>내용</p>", "내용", False)
    browser.save_draft("example", draft, close=True)
    page.keyboard.type.assert_called_once_with("제목", delay=40)
    page.keyboard.insert_text.assert_called_once_with("내용")
    save.click.assert_called_once()
    page.keyboard.press.assert_not_called()
    assert [call.args[0] for call in page.wait_for_timeout.call_args_list] == [250, 2500]


def test_successful_html_paste_does_not_duplicate_plain_text(monkeypatch):
    browser, context, page = fake_browser(monkeypatch)
    title, body, save = Mock(), Mock(), Mock()
    title.evaluate.return_value = "제목"
    body.evaluate.side_effect = ["", None, "내용"]
    save.evaluate.return_value = "저장"
    monkeypatch.setattr(browser, "_find", Mock(side_effect=[title, body, save]))
    browser.save_draft("example", NaverDraft("제목", "<p>내용</p>", "내용", False), close=True)
    context.grant_permissions.assert_called_once_with(["clipboard-read", "clipboard-write"])
    page.keyboard.press.assert_called_once_with("Control+V")
    page.keyboard.insert_text.assert_not_called()


def test_login_waits_for_cookie_without_credentials(monkeypatch, capsys):
    browser, context, page = fake_browser(monkeypatch)
    page.is_closed.return_value = False
    context.cookies.side_effect = [[], [{"name": "NID_AUT"}]]
    browser.login()
    assert "로그인 확인됨" in capsys.readouterr().out
    page.keyboard.type.assert_not_called()
    page.wait_for_timeout.assert_called_once_with(500)


def test_closed_login_window_is_cancelled(monkeypatch):
    browser, context, page = fake_browser(monkeypatch)
    page.is_closed.return_value = True
    with pytest.raises(RuntimeError, match="중단"):
        browser.login()
    context.cookies.assert_not_called()


def test_login_times_out_after_five_minutes(monkeypatch):
    browser, context, page = fake_browser(monkeypatch)
    monkeypatch.setattr(naver_browser.time, "monotonic", Mock(side_effect=[0, 301]))
    with pytest.raises(RuntimeError, match="5분 안에"):
        browser.login()
    context.cookies.assert_not_called()


@pytest.mark.parametrize("inserted", ["내용", ""])
def test_empty_html_paste_falls_back_and_checks_inserted_body(monkeypatch, inserted):
    browser, context, page = fake_browser(monkeypatch)
    title, body, save = Mock(), Mock(), Mock()
    title.evaluate.return_value = "제목"
    body.evaluate.side_effect = ["", None, "", inserted]
    save.evaluate.return_value = "저장"
    monkeypatch.setattr(browser, "_find", Mock(side_effect=[title, body, save]))
    draft = NaverDraft("제목", "<p>내용</p>", "내용", False)
    if inserted:
        browser.save_draft("example", draft, close=True)
        save.click.assert_called_once()
    else:
        with pytest.raises(RuntimeError, match="본문 입력을 확인하지 못해"):
            browser.save_draft("example", draft, close=True)
        save.click.assert_not_called()
    page.keyboard.insert_text.assert_called_once_with("내용")


def test_default_review_waits_for_enter(monkeypatch):
    browser, context, page = fake_browser(monkeypatch)
    title, body, save = Mock(), Mock(), Mock()
    title.evaluate.return_value = "제목"
    body.evaluate.side_effect = ["", None, "내용"]
    save.evaluate.return_value = "저장"
    monkeypatch.setattr(browser, "_find", Mock(side_effect=[title, body, save]))
    entered = Mock(return_value="")
    monkeypatch.setattr(builtins, "input", entered)
    browser.save_draft("example", NaverDraft("제목", "<p>내용</p>", "내용", False))
    entered.assert_called_once()
    assert "Enter" in entered.call_args.args[0]


def test_body_measurement_uses_stable_container_after_paragraph_replacement(monkeypatch):
    browser, context, page = fake_browser(monkeypatch)
    body = Mock()
    body.evaluate.side_effect = RuntimeError("최초 문단 교체됨")
    container = page.locator.return_value
    container.count.return_value = 1
    container.nth.return_value.is_visible.return_value = True
    container.nth.return_value.evaluate.return_value = "붙여넣은 내용"
    assert browser._body_text(body) == "붙여넣은 내용"
    body.evaluate.assert_not_called()


def test_failed_step_saves_screenshot(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    browser = NaverBrowser()
    browser.page = Mock()
    browser.page.is_closed.return_value = False
    browser.stage = "body"
    browser._failure()
    target = browser.page.screenshot.call_args.kwargs["path"]
    assert target.startswith("logs") and target.endswith("_body.png")
    assert "[body] 실패 화면" in capsys.readouterr().out


def test_find_searches_frame_and_role_before_css(monkeypatch):
    browser = NaverBrowser()
    page, frame = Mock(), Mock()
    page.url = frame.url = "https://blog.naver.com/example/postwrite"
    page.frames = [frame]
    page.get_by_text.return_value.count.return_value = 0
    page.get_by_role.return_value.count.return_value = 0
    frame.get_by_role.return_value.count.return_value = 1
    target = frame.get_by_role.return_value.nth.return_value
    target.is_visible.return_value = True
    browser.page = page
    found = browser._find([lambda s: s.get_by_role("button", name="저장", exact=True),
                           lambda s: s.locator(".fallback")], timeout=0)
    assert found is target
    frame.get_by_role.assert_called_once_with("button", name="저장", exact=True)
    page.locator.assert_not_called()
    frame.locator.assert_not_called()


def test_missing_playwright_has_install_help(monkeypatch):
    original = builtins.__import__

    def importing(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise ImportError("선택 의존성 없음")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importing)
    with pytest.raises(NaverSetupRequired, match="uv run --extra naver playwright install chromium"):
        with NaverBrowser()._browser():
            pass


def test_chrome_falls_back_to_chromium_and_closes(tmp_path, monkeypatch):
    playwright = Mock()
    context = Mock()
    context.pages = [Mock()]
    playwright.chromium.launch_persistent_context.side_effect = [RuntimeError("Chrome 없음"), context]

    @contextmanager
    def sync_playwright():
        yield playwright

    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=sync_playwright))
    monkeypatch.setenv("ABBYS_NAVER_PROFILE", str(tmp_path / "profile"))
    browser = NaverBrowser()
    monkeypatch.setattr(browser, "_step", lambda *args: None)
    with browser._browser() as (actual, page):
        assert actual is context
        assert page is context.pages[0]
    calls = playwright.chromium.launch_persistent_context.call_args_list
    assert calls[0].kwargs == {"channel": "chrome", "headless": False}
    assert calls[1].kwargs == {"headless": False}
    context.close.assert_called_once()


@pytest.mark.parametrize("safe", [True, False])
def test_browser_failure_preserves_only_safe_explanations(tmp_path, monkeypatch, safe):
    playwright, context = Mock(), Mock()
    context.pages = [Mock()]
    playwright.chromium.launch_persistent_context.return_value = context

    @contextmanager
    def sync_playwright():
        yield playwright

    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=sync_playwright))
    monkeypatch.setenv("ABBYS_NAVER_PROFILE", str(tmp_path / "profile"))
    browser = NaverBrowser()
    monkeypatch.setattr(browser, "_step", lambda *args: None)
    monkeypatch.setattr(browser, "_failure", Mock())
    error = (naver_browser.NaverInteractionError("5분 안에 로그인이 확인되지 않았습니다.")
             if safe else RuntimeError("브라우저 내부 원문"))
    with pytest.raises(RuntimeError) as caught:
        with browser._browser():
            browser.stage = "login"
            raise error
    assert "[login]" in str(caught.value)
    assert ("5분" in str(caught.value)) is safe
    assert "브라우저 내부 원문" not in str(caught.value)
    browser._failure.assert_called_once()
    context.close.assert_called_once()
