"""사용자가 로그인한 로컬 브라우저에서 네이버 초안만 임시저장한다."""

from contextlib import contextmanager
from datetime import datetime
import os
from pathlib import Path
import random
import re
import time
from urllib.parse import urlsplit

from frame.core.naver import NaverDraft, NaverLoginRequired, NaverSetupRequired


INSTALL_HELP = ("네이버 기능에는 Playwright가 필요합니다. uv run --extra naver frame naver login / "
                "uv run --extra naver playwright install chromium 을 실행하세요.")


class NaverInteractionError(RuntimeError):
    """브라우저 원문 오류 대신 사용자에게 전달할 안전한 안내."""


def is_publish_label(label: str) -> bool:
    """공백으로 나뉜 발행 문구도 금지한다."""
    return "발행" in re.sub(r"[\s\u200b-\u200d\ufeff]+", "", label)


def guarded_click(locator) -> None:
    """모든 자동 클릭 직전에 표시 문구와 접근성 라벨을 검사한다."""
    labels = locator.evaluate("""el => {
        const node = el.closest('button, a, [role="button"]') || el;
        return [node.textContent, node.getAttribute('aria-label'), node.title,
                node.getAttribute('value')].filter(Boolean).join(' ');
    }""")
    if is_publish_label(labels):
        raise RuntimeError("발행 요소는 자동으로 클릭할 수 없습니다.")
    locator.click(timeout=5000)


def profile_path() -> Path:
    path = Path(os.environ.get("ABBYS_NAVER_PROFILE", "~/.abbys/naver-profile")).expanduser().resolve()
    if any((parent / ".git").exists() for parent in (path, *path.parents)):
        raise NaverSetupRequired("ABBYS_NAVER_PROFILE은 저장소 밖 폴더로 지정하세요.")
    return path


class NaverBrowser:
    """비밀번호를 받지 않으며 한 번에 초안 한 개만 처리한다."""

    def __init__(self):
        self.stage = "start"
        self.page = None

    def _step(self, stage: str, message: str) -> None:
        self.stage = stage
        print(f"[{stage}] {message}")
        time.sleep(random.uniform(0.5, 1.5))

    def _failure(self) -> None:
        target = Path("logs") / f"naver_{datetime.now():%Y%m%d_%H%M%S_%f}_{self.stage}.png"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if self.page is None or self.page.is_closed():
                raise RuntimeError("창이 닫혔습니다.")
            self.page.screenshot(path=str(target), full_page=True, timeout=5000)
            print(f"[{self.stage}] 실패 화면: {target}")
        except Exception:
            print(f"[{self.stage}] 브라우저가 없거나 닫혀 스크린샷을 저장하지 못했습니다.")

    @contextmanager
    def _browser(self):
        self.page = None
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise NaverSetupRequired(INSTALL_HELP) from exc
        path = profile_path()
        context = None
        with sync_playwright() as playwright:
            try:
                self._step("browser", "브라우저 열기")
                try:
                    context = playwright.chromium.launch_persistent_context(
                        str(path), channel="chrome", headless=False)
                except Exception:
                    print("설치된 Chrome을 열 수 없어 번들 Chromium으로 다시 시도합니다.")
                    try:
                        context = playwright.chromium.launch_persistent_context(str(path), headless=False)
                    except Exception as exc:
                        raise NaverSetupRequired("브라우저를 열지 못했습니다. 프로필 사용 중 여부를 확인하세요. "
                                                 + INSTALL_HELP) from exc
                context.set_default_timeout(5000)
                self.page = context.pages[0] if context.pages else context.new_page()
                yield context, self.page
            except (NaverLoginRequired, NaverSetupRequired):
                self._failure()
                raise
            except NaverInteractionError as exc:
                self._failure()
                raise RuntimeError(f"[{self.stage}] {exc}") from exc
            except Exception as exc:
                self._failure()
                raise RuntimeError(f"[{self.stage}] 작업 실패. 창을 닫았다면 작업이 중단됩니다. "
                                   "HTML을 열어 수동으로 붙여넣거나 화면을 확인하세요.") from exc
            finally:
                if context is not None:
                    try:
                        context.close()
                    except Exception:
                        pass

    def login(self) -> None:
        with self._browser() as (context, page):
            self._step("login", "열린 창에서 직접 로그인하세요. 최대 5분 기다립니다.")
            page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded")
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                if page.is_closed():
                    raise NaverInteractionError("창을 닫아 로그인을 중단했습니다.")
                if any(cookie["name"] == "NID_AUT" for cookie in context.cookies("https://www.naver.com")):
                    print("로그인 확인됨")
                    return
                page.wait_for_timeout(500)
            raise NaverInteractionError("5분 안에 로그인이 확인되지 않았습니다. frame naver login을 다시 실행하세요.")

    def _scopes(self):
        return [self.page, *[frame for frame in self.page.frames if frame != self.page.main_frame]]

    def _check_login(self) -> None:
        if any(urlsplit(scope.url).hostname == "nid.naver.com" for scope in self._scopes()):
            raise NaverLoginRequired("frame naver login 먼저 실행하세요.")
        if self.page.get_by_text("해당 블로그가 없습니다").count():
            raise NaverSetupRequired("블로그 ID를 찾을 수 없습니다. blog.naver.com/<아이디> 의 아이디를 확인하세요.")

    def _find(self, factories, *, timeout=15000):
        deadline = time.monotonic() + timeout / 1000
        while True:
            self._check_login()
            for factory in factories:
                for scope in self._scopes():
                    locator = factory(scope)
                    for index in range(locator.count()):
                        item = locator.nth(index)
                        if item.is_visible():
                            return item
            if time.monotonic() >= deadline:
                return None
            self.page.wait_for_timeout(250)

    def _dismiss(self) -> None:
        # 이어쓰기를 승인하지 않고 취소만 한다. 알려진 클래스는 폴백이다.
        for factories in (
            [lambda s: s.get_by_role("button", name="취소", exact=True),
             lambda s: s.locator(".se-popup-button-cancel")],
            [lambda s: s.get_by_role("button", name=re.compile(r"도움말.*닫기|닫기.*도움말")),
             lambda s: s.locator(".se-help-panel-close-button")],
        ):
            item = self._find(factories, timeout=2000)
            if item is not None:
                guarded_click(item)

    def _body_text(self, body) -> str:
        # 붙여넣기로 최초 문단이 교체될 수 있으므로 독립적으로 본문 컨테이너를 다시 찾는다.
        target = body
        for scope in self._scopes():
            containers = scope.locator(".se-content")
            for index in range(containers.count()):
                candidate = containers.nth(index)
                if candidate.is_visible():
                    target = candidate
                    break
            if target is not body:
                break
        return target.evaluate("""el => {
            const copy = el.cloneNode(true);
            copy.querySelectorAll('.se-title-text, .se-documentTitle, .se-placeholder')
                .forEach(n => n.remove());
            return (copy.value || copy.textContent || '').replace(/[\\s\\u200b-\\u200d\\ufeff]/g, '');
        }""")

    def save_draft(self, blog_id: str, draft: NaverDraft, *, close: bool = False) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", blog_id):
            raise NaverSetupRequired("블로그 ID에는 영문, 숫자, 밑줄, 하이픈만 사용하세요.")
        with self._browser() as (context, page):
            if not any(cookie["name"] == "NID_AUT" for cookie in context.cookies("https://www.naver.com")):
                raise NaverLoginRequired("로그인 정보가 없습니다. frame naver login 먼저 실행하세요.")
            self._step("editor", "블로그 편집기 열기")
            page.goto(f"https://blog.naver.com/{blog_id}/postwrite", wait_until="domcontentloaded")
            self._check_login()
            self._step("dialogs", "이어쓰기 취소 및 도움말 닫기")
            self._dismiss()
            self._step("title", "제목 입력")
            title = self._find([lambda s: s.get_by_role("textbox", name="제목", exact=True),
                                lambda s: s.get_by_placeholder("제목", exact=True),
                                lambda s: s.locator(".se-title-text")])
            if title is None:
                raise RuntimeError("제목 입력란을 찾지 못했습니다.")
            guarded_click(title)
            page.keyboard.type(draft.title, delay=40)
            self._step("body", "본문 붙여넣기")
            body = self._find([lambda s: s.get_by_role("textbox", name="본문", exact=True),
                               lambda s: s.get_by_placeholder("본문", exact=True),
                               lambda s: s.locator(".se-component.se-text [contenteditable='true']"),
                               lambda s: s.locator(".se-component.se-text"),
                               lambda s: s.locator(".se-content")])
            if body is None:
                raise RuntimeError("본문 입력란을 찾지 못했습니다.")
            guarded_click(body)
            try:
                context.grant_permissions(["clipboard-read", "clipboard-write"])
                body.evaluate("""async (el, data) => {
                    await navigator.clipboard.write([new ClipboardItem({
                        'text/html': new Blob([data.html], {type: 'text/html'}),
                        'text/plain': new Blob([data.plain], {type: 'text/plain'})
                    })]);
                }""", {"html": draft.html, "plain": draft.plain})
                page.keyboard.press("Control+V")
                page.wait_for_timeout(1000)
            except Exception:
                print("HTML 클립보드를 사용할 수 없어 본문을 확인하고 일반 텍스트로 대체합니다.")
            text = self._body_text(body)
            if not text:
                page.keyboard.insert_text(draft.plain)
                page.wait_for_timeout(250)
                if not self._body_text(body):
                    raise NaverInteractionError("본문 입력을 확인하지 못해 임시저장을 중단했습니다. HTML을 수동으로 붙여넣으세요.")
            self._step("save", "임시저장 버튼 클릭")
            save = self._find([lambda s: s.get_by_role("button", name="저장", exact=True)])
            if save is None:
                raise RuntimeError("정확히 '저장'인 버튼을 찾지 못했습니다.")
            guarded_click(save)
            page.wait_for_timeout(2500)
            print("임시저장 버튼을 눌렀습니다. 저장 상태와 본문을 사람이 확인하세요.")
            if not close:
                self._step("review", "브라우저에서 확인·경험 채우기·발행은 직접 하세요.")
                try:
                    input("확인을 마친 뒤 Enter를 누르면 브라우저가 닫힙니다: ")
                except EOFError:
                    raise NaverInteractionError("입력 가능한 터미널이 필요합니다. 자동 종료는 --close를 사용하세요.")
