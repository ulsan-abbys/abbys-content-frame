# avis-content-frame

울산 지역 AI 스터디가 블로그 초안과 숏폼 영상 작업을 함께 개선하는 작은 공통 틀입니다. 각자 설정과 어댑터를 바꾸고, 검증한 개선을 PR로 나눕니다.

```text
N1 이슈 수집
  -> N2 검색 수요
  -> N3 주제 후보
  -> [G1 주제 승인]
  -> N4 리서치·출처
  -> N5 초안
  -> N6 기계 점검 -- 실패 --> N5 (최대 2회)
  -> [G2 경험·사실 검수]
       +-> N7 서식·이미지 -> N8 게시 준비 -> [G3 게시 클릭: 항상 사람]
       +-> V1 대본 추출 -> [G4 대본 낭독]
             -> V2 렌더링 -> V3 영상 점검 -> [G5 업로드 클릭: 항상 사람]
```

이 그림의 정본은 `config/graph.toml`입니다. `auto`는 자동화할 수 있는 노드라는 뜻이며, 전체 흐름을 실행하는 엔진은 아직 없습니다. 현재 제공하는 것은 초안 점검, 관문 기록·단계 계산, 그래프 표시, 외부 도구 호출입니다. N6 재작성 반복 상한도 설계 데이터이며 CLI가 자동 반복하지 않습니다. 노드별 실제 상태는 `modules/`에서 확인합니다.

## 5분 시작

Python 3.11 이상을 준비하고 Windows PowerShell에서 실행합니다. `ulsan-avis`은 운영자가 알려준 GitHub 소유자 이름으로 바꿉니다.

```powershell
git clone https://github.com/ulsan-avis/avis-content-frame
cd avis-content-frame
uv venv; uv pip install -e .[dev]
.\.venv\Scripts\Activate.ps1
copy config\profile.example.toml config\profile.toml
frame gate status
frame graph
python -m pytest -q
```

`uv` 없이 표준 `venv`와 `pip`를 사용해도 됩니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
copy config\profile.example.toml config\profile.toml
```

활성화가 제한된 환경에서는 `.\.venv\Scripts\python.exe -m frame`으로 실행할 수 있습니다. 기본 설정 경로는 현재 작업 폴더의 `config/`이므로 저장소 루트에서 실행합니다. `profile.toml`이 없으면 `profile.example.toml`을 사용합니다.

examples/clinic/ — 시연 예시: 가상의 동네 피부과 원장 블로그 (규칙 파일 3개 + 초안 + 쇼츠 대본)

운영자가 예시 파일을 추가한 뒤에는 다음 명령으로 점검합니다.

```powershell
frame check examples\clinic\초안\01_겨울철-가려움-보습.md
frame gate status
```

아직 예시가 없으면 저장소에 포함된 테스트용 초안으로 바로 확인합니다.

```powershell
frame check tests\fixtures\good.md
frame check tests\fixtures\bad.md
```

두 번째 명령은 의도적으로 실패합니다. 실패 종료 코드는 1입니다. 본문은 `## 출처` 앞부분이며 공백을 제외한 글자 수, 본문의 `## ` 소제목 수, 출처 구역에서 웹 주소가 있는 줄 수, 경험 슬롯 수를 검사합니다. 출처 주소 개수 검사는 링크 유효성이나 주장 정확성을 보장하지 않습니다. 경험 슬롯은 최종 공개 전에 사람이 실제 내용으로 채우고 검수합니다.

## AI에게 맡기기 / 실습 / 새 모듈 만들기

| 하고 싶은 일 | 안내 |
|---|---|
| AI에게 설치·분야 변경·초안 점검 맡기기 | [AI에게 맡기기](docs/AI에게_맡기기.md) |
| 모임에서 30분 동안 직접 해 보기 | [실습 30분](docs/실습_30분.md) |
| 규칙팩·어댑터·노드 확장하기 | [새 모듈 만들기](docs/새_모듈_만들기.md) |

Claude Code용 스킬은 [frame-customize](.claude/skills/frame-customize/SKILL.md)와 [new-module](.claude/skills/new-module/SKILL.md)입니다. 각각 분야 변경과 모듈 추가 절차를 담고 있습니다. Codex에는 해당 파일을 읽고 따르도록 요청할 수 있습니다.

## 구조

```text
avis-content-frame/
  config/
    profile.example.toml      화자·말투·분량·영상 기준
    rules/                    업종별 규칙 팩
    graph.toml                노드·연결·사람 관문
  src/frame/
    core/                     순수 모델·점검·관문·포트
    adapters/                 외부 CLI·HTTP·로그·자료 수집
    config_loader.py          TOML 읽기와 모델 생성
    cli.py                    명령 입력과 의존성 조립
    __main__.py               python -m frame 진입점
  modules/                    노드별 역할과 모집 상태
  tests/                      네트워크 없는 테스트·초안 예시
  .github/                    Issue·PR 양식
```

**core는 바깥을 모릅니다.** `core/`는 표준 라이브러리만 사용하는 순수 도메인으로, 문자열과 모델을 받아 결과를 돌려줍니다. 파일·네트워크·프로세스 I/O와 `frame.adapters`, `frame.cli` 의존은 금지합니다. core에 정의한 포트를 adapters가 구현하고, `cli.py`와 `config_loader.py`에서 조립합니다. 테스트는 포트에 가짜 구현을 넣으며 `tests/test_architecture.py`가 core의 금지 의존성을 검사합니다. 런타임 의존성은 없고 개발 의존성은 `pytest`입니다.

## 내 것으로 바꾸는 4곳

| 위치 | 바꿀 내용 | 확인 방법 |
|---|---|---|
| 1. `config/profile.toml` | 내 분야·지역·말투·분량·영상 길이 | `frame check`로 분량 등 점검 |
| 2. `config/rules/*.toml` | 내 업종 금칙어·정규식·오류/경고 | 규칙별 허용·차단 예시 테스트 |
| 3. `src/frame/adapters/` | 다른 AI·다른 영상 도구 | 같은 포트를 구현하고 가짜 구현으로 테스트 |
| 4. `config/graph.toml` | 노드·연결·관문 추가 | 모듈 카드와 연결 검증 테스트도 갱신 |

`persona`와 `style`은 작성 도구에 연결할 설정이며 현재 얇은 `frame write` 명령이 자동으로 프롬프트에 넣지는 않습니다. `forbid_emoji`는 문체 지침이고, 현재 예시 규칙 팩의 이모지 발견은 경고입니다. 엄격한 차단이 필요하면 해당 규칙의 `severity`를 `error`로 바꿉니다. 의료 규칙의 조문 표시는 요청된 예시의 검토 힌트이며 법률 판단이나 심의 통과를 보장하지 않습니다.

외부 도구 호출 예시는 다음과 같습니다. Claude CLI와 MoneyPrinterTurbo는 별도 설치가 필요하며 이 저장소의 Python 의존성에 포함하지 않습니다.

```powershell
frame write .
$env:MPT_DIR = "C:\도구\MoneyPrinterTurbo"
frame render .\대본.txt --out .\출력
```

`frame write`는 지정한 작업 폴더에서 Claude CLI에 `STATE.md 보고 지금 하는 일을 이어서 해줘.`를 전달합니다. Claude는 `acceptEdits` 모드로 실행되므로 해당 폴더의 파일을 수정할 수 있습니다. 영상 렌더링용 로컬 소재·음성·글꼴은 `MoneyPrinterTurboRenderer` 어댑터 설정으로 교체합니다.

## 사람 관문과 단계적 자동화

| 단계 | 사람 검토 | 의미 |
|---|---|---|
| L0 | 매번 | 기본 단계, 사람이 결과를 직접 확인 |
| L1 | 실행 번호가 3의 배수일 때 | 세 번 중 한 번 표본 검토 |
| L2 | 생략 가능 | 누적 이력을 바탕으로 검토 자동화 |
| HUMAN_ONLY | 항상 | 게시·업로드 클릭은 자동화하지 않음 |

관문별 기록 중 마지막 기계 누락 이후의 최근 10건을 봅니다. 10건이 쌓였고 그중 `approved`가 9건 이상이며 기계 누락이 한 번도 없으면 한 단계 승급합니다. 창은 이동하며 같은 기록을 포함할 수 있고 승급 후 새 10건을 기다리는 방식은 아닙니다. `edited`와 `rejected`는 승인 수에 포함하지 않습니다. 가장 최근 기록에서 `missed_by_machine`이 참이면 즉시 L0로 강등하고, 이후 새 기록을 모읍니다.

G1 주제 승인과 G4 대본 낭독은 L0에서 시작해 최대 L2까지, G2 경험·사실 검수는 최대 L1까지 올라갑니다. G3 게시 클릭과 G5 업로드 클릭은 `HUMAN_ONLY`로 고정합니다. 현재 단계 계산과 기록은 검토를 돕는 도구이며 실제 게시·업로드를 실행하지 않습니다.

```powershell
frame gate record --gate G2 --decision approved --run-id "연습-001" --note "출처와 경험을 직접 확인"
frame gate record --gate G2 --decision edited --missed-by-machine --note "기계가 놓친 사실 오류를 수정"
frame gate status
```

관문 로그 기본 위치는 `logs/gates.jsonl`입니다. 로그에는 실명·환자 정보·비밀을 적지 않습니다. `--log` 옵션으로 연습용 로그를 분리할 수 있습니다. `frame gate record --help`와 `frame gate status --help`에서 사용 위치를 확인합니다.

## 함께 고치는 법

버그·개선 제안·모듈 카드 Issue로 문제와 기대 결과를 먼저 공유합니다. 개선 방향은 Discussions 또는 모임에서 정하고, fork → 작업 브랜치 → PR로 제안합니다. N1·N2는 비어 있으므로 공식 데이터 수집을 맡을 사람을 모집합니다.

PR에는 변경한 동작을 확인하는 테스트가 필수입니다. 규칙을 추가하면 허용·차단 예시를 함께 넣고, 어댑터를 바꾸면 테스트가 네트워크나 외부 프로그램 없이 돌아가도록 가짜 구현을 사용합니다. 모듈을 맡으면 카드의 입력·출력·끝 기준·상태를 갱신하고 결과를 공유합니다.

```powershell
git switch -c feat/my-module
python -m pytest -q
```

## 하지 않는 것

- 자동 게시·자동 업로드 클릭
- 봇 탐지 우회
- 키·비밀번호·토큰 커밋
- 기계 점검 통과를 사실·의료·법률 검수 완료로 간주

라이선스는 MIT이며 저작권자는 Ulsan Avis AI contributors입니다.
