"""기존 파일을 덮어쓰지 않고 일반 블로그 작업 폴더를 만듭니다."""

import json
from pathlib import Path
import re


AGENTS_TEMPLATE = """# 일반 블로그 작업실

## 작업 순서
1. STATE.md와 profile.toml을 읽고 지금 하는 일을 확인합니다.
2. 초안은 초안/에 저장하고 STATE.md의 진행 상황을 갱신합니다.
3. 점검표 대조 결과는 출처 구역 뒤에 적습니다.

## 끝 기준
- profile.toml의 draft 기준을 따릅니다. 기본 본문 분량은 공백 제외 1200~1800자입니다.
- 본문 소제목은 '## '로 시작하는 3개입니다.
- '## 출처' 구역에 주제를 직접 뒷받침하는 출처 URL을 줄마다 하나씩 2개 이상 적습니다.
- [내 경험] 슬롯을 2개 비워 둡니다. 사람이 실제 경험을 채우고 검수합니다.
- 기준을 바꾸면 profile.toml과 이 문서도 함께 맞춥니다.

## 점검표
- 분량·소제목·출처·경험 슬롯이 끝 기준과 일치하는가?
- 출처 페이지를 직접 열어 본문의 주장을 뒷받침하는지 확인했는가?
- 경험·사례·수치·URL을 지어내지 않았는가? 확인 못 한 내용은 [확인 필요]로 표시합니다.
- 효과 보장·과장·근거 없는 단정 표현을 제거했는가?
- profile.toml의 화자·분야·지역·목적·말투·이모지 지침을 따랐는가?

## 사람 검수
- 기계 점검 통과 후에도 사실·출처·경험은 사람이 확인합니다.
- 게시·업로드는 항상 사람이 직접 합니다. 자동 게시와 비밀번호 자동 입력은 금지합니다.
- 네이버 임시저장은 frame naver draft로 할 수 있습니다. 로그인은 열린 창에서 사람이 직접 합니다.
"""

STATE_TEMPLATE = """# 작업 상태

## 지금 하는 일
- 첫 글의 주제를 정하고 profile.toml을 확인합니다.

## 다음에 할 일
- 초안을 작성하고 기계 점검을 실행합니다.
- 사람이 출처·사실·경험 슬롯을 검수합니다.
- 게시 여부를 사람이 결정합니다.
"""


def create_workspace(workdir: str, template: Path, *, field: str, name: str, region: str) -> None:
    destination = Path(workdir)
    if destination.exists() or destination.is_symlink():
        raise ValueError("작업 폴더가 이미 있습니다. 덮어쓰지 않습니다.")
    content = template.read_text(encoding="utf-8")
    for key, value in {"field": field, "name": name, "region": region}.items():
        content = re.sub(rf"(?m)^{key} = .*?$",
                         lambda match: f"{key} = {json.dumps(value, ensure_ascii=False)}", content)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "profile.toml").write_text(content, encoding="utf-8")
    (destination / "AGENTS.md").write_text(AGENTS_TEMPLATE, encoding="utf-8")
    (destination / "STATE.md").write_text(STATE_TEMPLATE, encoding="utf-8")
    (destination / "초안").mkdir()
