# abbys-content-frame

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

이 그림의 정본은 `config/graph.toml`입니다. `auto`는 자동화할 수 있는 노드라는 뜻이며, 전체 흐름을 실행하는 엔진은 아직 없습니다. 현재 제공하는 것은 초안 점검, 관문 기록·단계 계산, 그래프 표시, 외부 도구 호출입니다. `frame write --topic`은 초안 작성 뒤 계층 0 점검과 계층 1 출처 채점을 실행하고, 실패하면 기본 최대 2회 고쳐 쓴 뒤 G2 사람 검수로 넘깁니다. 노드별 실제 상태는 `modules/`에서 확인합니다.

## 5분 시작

필요한 것은 Git, [uv](https://docs.astral.sh/uv/), **Claude Code 또는 Codex CLI 중 하나(설치 후 로그인 필요)**입니다. 초안 작성·점검·사람 확인까지 1편 약 10분을 예상하세요. 주제와 출처에 따라 더 걸릴 수 있습니다. 파이썬은 uv가 알아서 받습니다. 아무것도 없는 노트북이라면 [abbys-ai-setup의 새 노트북 세팅](https://github.com/ulsan-abbys/abbys-ai-setup/blob/main/docs/새_노트북_세팅.md)부터 따라 하세요.

```powershell
git clone https://github.com/ulsan-abbys/abbys-content-frame
cd abbys-content-frame
uv run frame new my-blog --field "생활" --name "생활 기록자" --region "울산"
uv run frame write my-blog --topic "겨울철 실내 정리" --engine auto
uv run frame gate status
```

- 명령은 모두 **저장소 맨 위 폴더에서** `uv run frame ...`으로 실행합니다. 가상환경을 켤(Activate) 필요가 없습니다.
- `frame new`는 `profile.toml`, `AGENTS.md`, `STATE.md`, `초안/`를 만듭니다. 대상 폴더나 파일이 이미 있으면 덮어쓰지 않고 실패합니다.
- 피부과 예시를 점검할 때는 `frame check "examples/clinic/초안/01_겨울철-가려움-보습.md" --profile examples/clinic/profile.toml`을 사용합니다. **분량 미달 1건**은 일부러 짧게 둔 예시의 정상 결과입니다.
- `my-blog/profile.toml`에서 화자·말투·글 종류·경험 슬롯을 고칩니다. `write --profile`이 없으면 **작업폴더/profile.toml → config/profile.toml → config/profile.example.toml** 순으로 읽습니다. `check`와 `score`는 작업폴더 프로필을 `--profile`로 지정하세요.
- Git이 없으면 GitHub 페이지의 **Code → Download ZIP**으로 받아 압축을 풀어도 됩니다.
- 테스트: `uv run --extra dev python -m pytest -q`

examples/clinic/ — 시연 예시: 가상의 동네 피부과 원장 블로그 (규칙 파일 3개 + 초안 + 쇼츠 대본)

테스트용 초안으로도 확인할 수 있습니다.

```powershell
uv run frame check tests\fixtures\good.md
uv run frame check tests\fixtures\bad.md
```

두 번째 명령은 의도적으로 실패합니다. 실패 종료 코드는 1입니다. 본문은 `## 출처` 앞부분이며 공백을 제외한 글자 수, 본문의 `## ` 소제목 수, 출처 구역에서 웹 주소가 있는 줄 수, 경험 슬롯 수를 검사합니다. 출처 주소 개수 검사는 링크 유효성이나 주장 정확성을 보장하지 않습니다. 경험 슬롯은 최종 공개 전에 사람이 실제 내용으로 채우고 검수합니다.

## AI에게 맡기기 / 실습 / 새 모듈 만들기

처음 쓰는 사람은 `uv run frame setup topics`로 분야·독자·검색어를 저장하고,
`uv run frame setup doctor`로 CLI·주제·API 키 준비 상태를 확인할 수 있습니다.
작업 폴더의 프로필을 쓰면 두 명령에 `--profile my-blog/profile.toml`을 붙이세요.
[API 키 발급 가이드](docs/API_키_발급_가이드.md)에 질문 입력, 키 발급과 환경 변수 설정을 안내합니다.
주제 설정은 `[topics]`만 갱신하며 N1~N3 실행은 후속 구현 대상입니다.
doctor는 기존 `select_engine`으로 엔진을 선택하고 API 키 없이 CLI 존재를 확인합니다.
`--check-naver`를 지정할 때만 네이버 API에 한 번 요청하며, 테스트는 가짜 전송 구현을 사용합니다.

| 하고 싶은 일 | 안내 |
|---|---|
| AI에게 설치·분야 변경·초안 점검 맡기기 | [AI에게 맡기기](docs/AI에게_맡기기.md) |
| 모임에서 30분 동안 직접 해 보기 | [실습 30분](docs/실습_30분.md) |
| 규칙팩·어댑터·노드 확장하기 | [새 모듈 만들기](docs/새_모듈_만들기.md) |

Claude Code용 스킬은 [frame-customize](.claude/skills/frame-customize/SKILL.md)와 [new-module](.claude/skills/new-module/SKILL.md)입니다. 각각 분야 변경과 모듈 추가 절차를 담고 있습니다. Codex에는 해당 파일을 읽고 따르도록 요청할 수 있습니다.

## 구조

```text
abbys-content-frame/
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

`frame write --topic`은 `persona`의 name·field·region·purpose와 `style`의 tone·forbid_emoji를 최초 작성과 고쳐 쓰기 프롬프트에 넣습니다. `[writing]`의 genre(글 종류)·checklist(점검표 이름)·experience_label(경험 슬롯 이름)도 적용합니다. 일반 예시는 생활 정보·내 경험이며, 피부과 설정은 `examples/clinic/profile.toml`에 있습니다. `draft.human_slot_pattern`을 생략하면 experience_label에 맞는 패턴을 만듭니다. 명시했다면 슬롯 이름과 함께 수정하세요. `forbid_emoji`는 문체 지침이고, 현재 예시 규칙 팩의 이모지 발견은 경고입니다. 엄격한 차단이 필요하면 해당 규칙의 `severity`를 `error`로 바꿉니다. 의료 규칙의 조문 표시는 요청된 예시의 검토 힌트이며 법률 판단이나 심의 통과를 보장하지 않습니다.

외부 도구 호출 예시는 다음과 같습니다. 작성·출처 채점에는 **Claude Code 또는 Codex CLI 중 하나**를 별도로 설치하고 로그인해야 합니다. 영상 생성에는 MoneyPrinterTurbo가 별도로 필요합니다. 이 도구들은 Python 의존성에 포함하지 않습니다. `check`와 `new`는 AI CLI 없이도 실행됩니다.

```powershell
uv run frame write my-blog --engine codex
uv run frame write my-blog --topic "겨울철 실내 정리" --engine claude
uv run frame score my-blog/초안/01_겨울철-실내-정리.md --profile my-blog/profile.toml --engine auto
$env:FRAME_ENGINE = "codex" # --engine이 없을 때 적용
$env:MPT_DIR = "./tools/MoneyPrinterTurbo"
uv run frame render .\대본.txt --out .\출력
```

`write`와 `score`의 엔진 우선순위는 `--engine` → `FRAME_ENGINE` → `auto`입니다. `auto`는 PATH에서 claude → codex 순으로 첫 번째를 선택하며 첫 줄에 엔진 이름을 출력합니다. 실행 실패 후 다른 엔진으로 자동 재시도하지 않습니다. 둘 다 없으면 설치·로그인 안내와 종료코드 2를 반환합니다.

`frame write`는 `--topic`이 없으면 선택한 엔진에 `STATE.md 보고 지금 하는 일을 이어서 해줘.`를 전달합니다. 이어 하기의 기존 설정은 Claude `acceptEdits`, Codex `workspace-write`입니다. 파일 수정이 필요한 이어 하기는 claude 엔진을 권장합니다. Windows Codex 샌드박스에서는 쓰기가 제한될 수 있습니다. 프롬프트는 두 엔진 모두 표준 입력으로 전달합니다. Codex CLI 0.167.0의 로컬 도움말에서 `exec`, `-s`, `-C`, `--output-last-message`, 표준 입력 `-`를 확인했습니다. Codex 작성은 `-c web_search=live`로 웹 검색을 켜며, 판정은 임시 폴더에서 `read-only`와 `web_search=disabled`를 사용합니다. 웹 검색 모드는 [공식 설정 문서](https://learn.chatgpt.com/docs/config-file/config-reference)를 따릅니다. 마지막 응답은 `--output-last-message` 파일에서 받습니다. 영상 렌더링용 로컬 소재·음성·글꼴은 `MoneyPrinterTurboRenderer` 어댑터 설정으로 교체합니다.

## 네이버 블로그 임시저장

`frame naver draft`는 로컬 HTML 파일만 만듭니다. 별도 브라우저 의존성이나 블로그 ID 설정은 필요하지 않습니다.

```powershell
uv run frame naver draft 작업실/초안/01_생활-정보.md
uv run frame naver check 원고.md capture.json  # 임시저장 화면의 수집 JSON 대조
```

HTML 파일 열기 → [본문 복사] → 편집기 본문 클릭 → Ctrl+V → [제목 복사] → 제목 칸 클릭 → Ctrl+V → 확인 개수 대조 → 임시저장 → 발행은 직접

출력된 `초안.naver.html`을 사용하세요. 제목은 본문에서 제외되며 복사 버튼으로 각각 옮깁니다. 안내 바는 복사되지 않습니다.
점검표는 제외하고 경험 슬롯은 굵게 표시하며 경고합니다. 작업폴더 `profile.toml`의 `[writing] experience_label`도 적용합니다.
사람이 경험 슬롯을 채우고 사실·출처·서식·실제 저장 상태를 확인해야 합니다. 검사 통과는 게시 승인을 대신하지 않습니다.

상세 안내: [네이버 붙여넣기](docs/네이버_임시저장.md). 사용자 실행 절차와 계정 제재 위험: [브라우저 에이전트에게 맡기기](docs/브라우저_에이전트에게_맡기기.md).

## 준수 기준

- [네이버 이용약관](https://policy.naver.com/rules/service.html)(2026-10-01): 자동화 수단 로그인·게시·삽입·회원 ID/게시물 수집 금지 → 로그인·삽입 자동화 코드는 제공하지 않으며 기본 권장은 사람이 직접 붙여넣기입니다.
- [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html) robots.txt 준수 + 정직한 User-Agent. robots.txt 4xx는 허용, 5xx·네트워크 오류는 차단하며 출처의 403은 그대로 받아들입니다. 캐시는 출처(스킴·호스트·포트)별 최대 24시간입니다.
- [W3C WebDriver](https://www.w3.org/TR/webdriver/) 자동화 표시 은폐 금지.
- [정보통신망법 제48조](https://www.law.go.kr/법령/정보통신망이용촉진및정보보호등에관한법률/제48조): 접근 권한을 넘는 침입·정보통신망 장애 유발 행위를 금지합니다.
- Tor·VPN·IP 회전·스텔스/undetected 드라이버·캡차 우회는 지원하지 않으며 기여(PR)도 받지 않습니다.
- 네이버 데이터는 공식 API(데이터랩 등)만 사용합니다. 블로그·카페·포스트·지식인 회원 게시물은 HTTP 수집 전에 차단합니다.

## 사람 관문과 단계적 자동화

| 단계 | 사람 검토 | 의미 |
|---|---|---|
| L0 | 매번 | 기본 단계, 사람이 결과를 직접 확인 |
| L1 | 실행 번호가 3의 배수일 때 | 세 번 중 한 번 표본 검토 |
| L2 | 생략 가능 | 누적 이력을 바탕으로 검토 자동화 |
| HUMAN_ONLY | 항상 | 게시·업로드 클릭은 자동화하지 않음 |

관문별 기록 중 마지막 기계 누락 이후의 최근 10건을 봅니다. 10건이 쌓였고 그중 `approved`가 9건 이상이며 기계 누락이 한 번도 없으면 한 단계 승급합니다. 창은 이동하며 같은 기록을 포함할 수 있고 승급 후 새 10건을 기다리는 방식은 아닙니다. `edited`와 `rejected`는 승인 수에 포함하지 않습니다. 가장 최근 기록에서 `missed_by_machine`이 참이면 즉시 L0로 강등하고, 이후 새 기록을 모읍니다.

G1 주제 승인과 G4 대본 낭독은 L0에서 시작해 최대 L2까지, G2 경험·사실 검수는 최대 L1까지 올라갑니다. G3 게시 클릭과 G5 업로드 클릭은 `HUMAN_ONLY`로 고정합니다. 현재 단계 계산과 기록은 검토를 돕는 도구이며 실제 게시·업로드를 실행하지 않습니다.

2026-11-14 개정: `HUMAN_ONLY`는 CLI가 게시 승인을 스스로 생성하지 않는다는 의미입니다. 사용자가 대상 글·블로그의 공개 발행을 명시 승인했다면 별도 브라우저 에이전트가 발행 조작을 수행하고 게시물 URL·본문까지 검증할 수 있습니다. 기본은 임시저장이며 `.agent.txt` 생성 자체는 승인이 아닙니다. 미작성 경험 슬롯·확인 필요 문구가 남으면 발행하지 않습니다. Claude/Codex와 브라우저 도구는 교체 가능하고 Aside는 필수가 아닙니다. [실행 조건](docs/브라우저_에이전트에게_맡기기.md)을 따릅니다.

```powershell
uv run frame gate record --gate G2 --decision approved --run-id "연습-001" --note "출처와 경험을 직접 확인"
uv run frame gate record --gate G2 --decision edited --missed-by-machine --note "기계가 놓친 사실 오류를 수정"
uv run frame gate status
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

- 사용자 승인 없는 게시·무인 반복 게시·자동 업로드 클릭
- 봇 탐지 우회
- 키·비밀번호·토큰 커밋
- 기계 점검 통과를 사실·의료·법률 검수 완료로 간주

라이선스는 MIT이며 저작권자는 Ulsan Abbys AI contributors입니다.


`frame write --topic`에서는 frame이 파일 입출력을 전담합니다. 작업폴더의 `AGENTS.md` 전문과 선택한 프로필 지침을 프롬프트에 넣고, 고쳐 쓰기에는 현재 초안 전문도 넣습니다. AI는 파일을 읽거나 쓰지 않고 `<<<DRAFT`와 `DRAFT>>>` 독립 줄 사이에 완성 초안을 응답합니다. 마커가 없으면 가장 긴 `markdown` 코드블록을 사용하며, 둘 다 없으면 초안 없음으로 실패합니다. frame은 초안을 지정 경로에 UTF-8로 저장한 뒤 점검하고, 최종 결과를 `STATE.md`에 ISO 시각·초안 경로·기계 점검 통과/실패·라운드 번호(최초 0)로 추가합니다. Claude 작성은 `--allowedTools WebSearch WebFetch`, Codex 작성은 `-s read-only`와 웹 검색을 사용합니다. 출처 뒤의 `---`, 다음 `##` 제목 또는 `### 점검표`부터는 출처 점검·채점에서 제외합니다. 이는 사람 검수나 게시 승인을 대신하지 않습니다.
