"""외부 구현을 모른 채 필요한 동작만 선언하는 포트."""

from typing import Protocol

from frame.core.models import GateDecision
from frame.core.naver import NaverDraft


class BlogDraftSaver(Protocol):
    def login(self) -> None: ...

    def save_draft(self, blog_id: str, draft: NaverDraft, *, close: bool = False) -> None: ...


class LLMWriter(Protocol):
    def write(self, prompt: str, workdir: str) -> str: ...


class VideoRenderer(Protocol):
    def render(self, script: str, out_dir: str) -> str: ...


class UrlChecker(Protocol):
    def check(self, url: str, keywords: list[str]) -> bool: ...


class PageFetcher(Protocol):
    def fetch(self, url: str) -> str | None: ...


class SourceJudge(Protocol):
    def judge(self, title: str, body: str, label: str, page_text: str) -> dict: ...


class TrendSource(Protocol):
    def fetch(self, region: str, keywords: list[str]) -> list[dict]: ...


class GateLog(Protocol):
    def append(self, d: GateDecision) -> None: ...

    def read(self) -> list[GateDecision]: ...
