# 내 블로그 주제와 API 키 준비하기

API 키는 프로그램이 자료를 요청할 때 쓰는 전용 열쇠입니다. 먼저 주제를 정하고, 필요한 열쇠만 준비하세요. 아래 명령은 저장소 맨 위 폴더의 터미널에서 실행합니다. 설치는 [README의 5분 시작](../README.md#5분-시작)을 참고하세요. `uv`를 쓰면 아래 `frame` 앞에 `uv run`을 붙입니다.

## 1. 내 블로그가 쓸 내용 정하기

```text
frame setup topics
```

분야, 지역, 독자, 씨앗 검색어 3~10개, 제외할 주제, 이슈 출처 URL, 주당 글 수를 차례로 묻습니다. 씨앗 검색어는 앞으로 찾아볼 기본 낱말입니다. 예를 들어 정리, 산책, 장보기를 쉼표로 구분해 넣습니다. 제외할 주제와 출처가 없으면 Enter를 누르세요. 주당 글 수는 1 이상의 정수입니다.

기본 저장 위치는 `config/profile.toml`의 `[topics]`입니다. 다른 표는 보존합니다. 새 파일은 `config/profile.example.toml`의 기본 설정을 바탕으로 만듭니다. 작업 폴더의 프로필을 쓰려면 두 명령에 같은 경로를 지정하세요.

```text
frame setup topics --profile my-blog/profile.toml
frame setup doctor --profile my-blog/profile.toml
```

RSS는 새 소식 목록을 받는 주소입니다. **공식 사이트의 RSS 안내 페이지에서 링크를 직접 복사**하세요. 일반 뉴스 페이지 주소와 다를 수 있습니다. RSS를 제공하지 않으면 비워 두세요. 프로그램은 RSS 주소를 만들어 넣거나 자동으로 찾지 않습니다.

에이전트나 반복 작업에서는 아래 내용을 `topics.json`으로 저장할 수 있습니다. 키는 넣지 마세요.

```json
{
  "field": "생활",
  "region": "울산",
  "audience": "지역 생활 정보를 찾는 이웃",
  "seed_keywords": ["정리", "산책", "장보기"],
  "exclude": [],
  "issue_sources": [],
  "cadence_per_week": 2
}
```

```text
frame setup topics --from-json topics.json
```

이 명령은 주제 설정만 저장합니다. 저장 후 `frame research`로 N1~N3 조사를 실행하고 `runs/<실행번호>.topics.md`에서 G1 후보를 검토하세요. 예약 게시는 수행하지 않습니다. 기존 초안 작성용 `[persona]`와 `[writing]`은 별도로 유지됩니다.

## 2. 어느 단계에 어떤 키가 필요한가요?

| 단계 | 준비물 |
|---|---|
| AI 엔진 | API 키 없음. Claude Code 또는 Codex CLI 중 하나를 설치하고 구독 계정으로 로그인 |
| N1 이슈 수집 | 직접 붙여 넣은 RSS에는 키 없음. 기상특보를 쓸 때만 공공데이터포털 서비스키 선택 |
| N2 검색 수요 | NAVER API HUB 검색어 트렌드의 Client ID와 Client Secret (권장) |
| N3 주제 후보 / N4 리서치·출처 | 별도 API 키 없음. AI를 쓸 때는 위 엔진 로그인 필요 |

`frame setup doctor`는 CLI가 PATH(명령을 찾는 위치)에 있는지만 확인합니다. 로그인 완료나 구독 상태를 검사하지 않습니다. 사용할 CLI를 직접 실행해서 로그인하세요. 엔진 선택에는 기존 `select_engine`을 사용합니다. `FRAME_ENGINE`이 없으면 codex, claude 순으로 찾습니다. 둘 중 하나만 있으면 됩니다.

## 3. 네이버 열쇠 두 개 발급받기

### 권장: NAVER Cloud Platform의 NAVER API HUB

**2026-11 기준 안내, 화면이 다르면 화면을 따르세요.**

1. [NCP 콘솔](https://console.ncloud.com)에 본인 계정으로 로그인합니다.
2. **Menu → All Services → Application Services → NAVER API HUB**를 엽니다.
3. **Subscription**에서 **서비스 이용 신청**을 하고 약관에 동의합니다.
4. **Application 등록**에서 **Data Lab 검색어 트렌드**를 선택합니다.
5. **API 관리 → 인증 정보**에서 **Client ID / Client Secret**을 확인합니다.
6. 각각 `NAVER_HUB_CLIENT_ID`, `NAVER_HUB_CLIENT_SECRET` 환경 변수에 저장합니다.

요금·결제수단 등록 여부는 콘솔의 요금 화면에서 직접 확인하세요.

N2는 `POST https://naverapihub.apigw.ntruss.com/search-trend/v1/search`에
`X-NCP-APIGW-API-KEY-ID`, `X-NCP-APIGW-API-KEY` 인증 헤더로 요청합니다.
요청 본문은 기존 데이터랩과 같은 `startDate`, `endDate`, `timeUnit`, `keywordGroups`입니다.
결과는 **0~100의 상대 지수**이며 실제 검색 횟수가 아닙니다. 요청 범위에서 가장 큰 값을 100으로 놓으므로 서로 다른 요청의 수치를 실제 검색량처럼 비교하지 마세요.
[NAVER API HUB 검색어 트렌드 공식 문서](https://api.ncloud-docs.com/docs/naver-api-hub-search-trend)

### 기존 개발자센터: 이미 7/31 이전에 신청한 키만, 2027-06-30까지

2026-07-31부터 개발자센터의 검색 API·데이터랩 검색어트렌드·쇼핑인사이트 신규 신청이 차단되었으며 NAVER API HUB로 이전합니다.
기존 키의 유예 기한은 **2027-06-30**입니다.
[개발자센터 공식 공지](https://developers.naver.com/notice/article/32530)

7/31 이전에 해당 API를 신청한 키만 기존 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` 환경 변수로 사용하세요.
기존 앱이라도 차단 이후 데이터랩을 추가한 경우 HTTP 401 / 오류 코드 024 (`Scope Status Invalid`)가 발생할 수 있습니다(2026-11-14 실측).
이때 N2 실행 기록에는 다음 안내를 남깁니다.

> 2026-07-31 이후 개발자센터 신규 신청 차단 — NAVER API HUB 키(NAVER_HUB_CLIENT_ID/SECRET)를 발급해 넣으세요. docs/API_키_발급_가이드.md

HUB 키 두 개가 모두 있으면 HUB를 우선 사용합니다. 완전한 HUB 키 쌍이 없을 때만 기존 개발자센터 키 쌍으로 요청합니다.
선택한 백엔드는 N2 결과의 `backend`·`source`와 실행 기록의 `note`에 남습니다.
HUB 요청이 실패해도 개발자센터로 자동 재시도하지 않습니다. 키 값과 오류 응답 원문은 기록하지 않습니다.

## 4. 기상특보 서비스키 발급받기 (선택)

1. [공공데이터포털](https://www.data.go.kr)에 회원가입하고 로그인합니다.
2. [기상청_기상특보 조회서비스](https://www.data.go.kr/data/15000415/openapi.do)를 엽니다.
3. **활용신청**을 누르고 이용 목적 등 필수 항목을 적어 신청합니다.
4. **마이페이지**에서 활용신청 상태와 인증키를 확인합니다. 승인이 필요한 경우 완료된 뒤 사용합니다.
5. 인증키를 `DATA_GO_KR_SERVICE_KEY` 환경 변수에 저장합니다. 인증키 화면에서 일반 인증키의 Decoding 값을 사용하고, 향후 API 요청 시 어댑터가 URL 인코딩하도록 합니다.

이 단계는 기상특보를 이용할 때만 필요합니다. doctor는 키가 있는지만 확인하며 공공데이터포털에 실제 요청하지 않습니다.

## 5. 키를 내 컴퓨터에 저장하기

환경 변수는 프로그램이 내 컴퓨터에서 읽는 설정입니다. 아래 `발급받은_...` 부분을 본인의 값으로 바꾸세요. 실제 값을 채팅, 스크린샷, 프로필, JSON, 소스 코드에 붙이지 마세요. **키를 Git에 커밋하지 마세요.** 명령 기록이나 설정 파일에도 키가 남을 수 있으니 공유하지 마세요.

### Windows PowerShell

```powershell
setx NAVER_HUB_CLIENT_ID "발급받은_Client_ID"
setx NAVER_HUB_CLIENT_SECRET "발급받은_Client_Secret"
# 기상특보를 쓸 때만 실행합니다.
setx DATA_GO_KR_SERVICE_KEY "발급받은_서비스키"
```

`setx`는 새로 여는 터미널부터 적용됩니다. 터미널을 닫고 새로 여세요. 편집기 안의 터미널이라면 편집기도 완전히 종료했다가 다시 여세요. 저장소 폴더로 이동해서 점검합니다.

### macOS (기본 zsh 터미널)

터미널에서 `nano ~/.zshrc`를 실행하고 파일 끝에 다음 줄을 추가합니다. `Ctrl+O`, Enter로 저장하고 `Ctrl+X`로 나옵니다.

```sh
export NAVER_HUB_CLIENT_ID='발급받은_Client_ID'
export NAVER_HUB_CLIENT_SECRET='발급받은_Client_Secret'
# 기상특보를 쓸 때만 추가합니다.
export DATA_GO_KR_SERVICE_KEY='발급받은_서비스키'
```

`source ~/.zshrc`를 실행하거나 새 터미널을 열면 적용됩니다. `.zshrc`에는 키가 들어 있으므로 공개 저장소나 공유 자료에 넣지 마세요.

## 6. 준비 상태 확인하기

```text
frame setup doctor
```

항목별 있음/없음과 다음 할 일, 안내 문서 경로가 표시됩니다. 키의 실제 값은 출력하지 않습니다. 이 명령은 준비가 덜 되어도 종료 코드 0이며, 표에서 상태를 직접 확인해야 합니다. 일반 점검은 네트워크를 쓰지 않습니다.

네이버 키가 실제로 작동하는지도 확인하려면 다음 명령을 실행합니다.

```text
frame setup doctor --check-naver
```

완전한 키 쌍이 있으면 HUB 우선으로 네이버 공식 API에 작은 요청을 **한 번** 보냅니다. 사용 요금은 콘솔에서 확인하세요. `OK`는 HTTP 200 응답을 받았다는 뜻입니다. `HTTP 401`은 키와 신청 상태를 확인하고(개발자센터는 위 이전 안내 참고), `HTTP 403`은 사용 API 권한을 확인하세요. `HTTP 429`는 호출 한도를 확인하세요. 연결 실패는 인터넷 상태를 확인하세요. 키가 없으면 요청을 건너뜁니다. 오류의 응답 본문이나 키는 출력하지 않습니다.
