# N5 초안

## 하는 일

화자·문체·초안 기준을 반영하고 사람이 채울 경험 슬롯을 남깁니다.

## 입력

G1 승인 주제, N4 출처, 프로필

## 출력

마크다운 본문과 ## 출처 구역

## 끝 기준

소제목, 분량, 출처, 경험 슬롯을 갖춘 초안을 N6에 전달합니다.

## 실패 시 되돌아갈 곳

출처 부족은 N4, 표현·분량 수정은 N5로 돌아갑니다.

## 금지

허구의 개인 경험을 사실처럼 작성, 치료 효과 단정

## 지금 상태

주제 작성 모드는 frame이 AGENTS.md·프로필 읽기, 응답 초안 저장, STATE.md 결과 추가를 담당합니다. writer는 웹 조사 후 `<<<DRAFT` / `DRAFT>>>`로 초안 전문을 반환하며, 마커가 없을 때만 가장 긴 markdown 코드블록을 사용합니다. 재작성에는 현재 본문을 주입합니다. Windows 샌드박스 쓰기 제한에 대응하는 결정이며, core는 문자열 추출·반복만 담당합니다. 검증: `tests/test_pipeline.py`, `tests/test_engines_and_workspace.py`, `tests/test_architecture.py` (실제 CLI·네트워크 호출 없음).

`frame write <작업폴더> --topic "주제"`로 작성, 계층 0 기계 점검과 계층 1 출처 채점, 실패 시 고쳐 쓰기(기본 최대 2회)를 자동 실행합니다. 매 라운드 결과는 `logs/write_runs.jsonl`에 기록합니다. 통과해도 사람 검수 대기(G2)이며, 내용 정확성과 경험은 사람이 확인하고 게시 클릭은 사람이 수행합니다.

## 맡은 사람




작성 엔진은 `--engine auto|claude|codex` 또는 `FRAME_ENGINE`으로 선택합니다. auto는 PATH의 Claude → Codex 순이며 한 CLI만 있어도 동작합니다. `frame new`로 일반 블로그 작업실을 생성할 수 있습니다. 작업폴더 프로필의 writing·persona·style을 작성 및 재작성 지침에 반영합니다. 피부과 설정은 `examples/clinic/profile.toml`을 사용합니다. 검증 근거: `tests/test_engines_and_workspace.py`, `tests/test_pipeline.py`, `tests/test_architecture.py`. 실제 로그인·원격 생성은 자동 테스트 범위 밖입니다.
