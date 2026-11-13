"""RSS·데이터랩 입출력과 노드별 재개 가능한 조사 기록."""

from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener
import xml.etree.ElementTree as ET

from frame.adapters.crawl_http import can_fetch
from frame.adapters.setup import GUIDE, NAVER_KEY_NAMES, NAVER_MIGRATION_NOTE, NoRedirect, naver_connection
from frame.core.ports import LLMWriter, ResearchTransport
from frame.core.research import render_topics, topic_prompt, validate_candidates

USER_AGENT = "abbys-content-frame/0.x"


class HttpResearchTransport:
    def request(self, method: str, url: str, headers: dict[str, str],
                body: bytes | None = None) -> tuple[int, bytes]:
        if method == "GET" and not can_fetch(url):
            return 403, b""
        request = Request(url, headers=headers, data=body, method=method)
        try:
            # 이동과 재시도 없이 소스당 한 번 요청합니다. 인증 헤더도 이동하지 않습니다.
            with build_opener(NoRedirect()).open(request, timeout=10) as response:
                return response.status, response.read()
        except HTTPError as exc:
            try:
                return exc.code, exc.read()
            finally:
                exc.close()


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_issues(topics: dict, transport: ResearchTransport) -> tuple[str, list, str]:
    sources = list(dict.fromkeys(topics["issue_sources"]))
    if not sources:
        return "skipped", [], f"이슈 출처가 없습니다. RSS/Atom 주소 설정 안내: {GUIDE}"
    items, seen, failures = [], set(), 0
    terms = [term.casefold() for term in topics["seed_keywords"] + [topics["region"]] if term]
    for source in sources:
        try:
            status, body = transport.request("GET", source, {"User-Agent": USER_AGENT})
            if status != 200:
                failures += 1
                continue
            root = ET.fromstring(body)
            if root.tag.rsplit("}", 1)[-1] not in ("rss", "feed", "RDF"):
                failures += 1
                continue
            fetched_at = timestamp()
            for entry in root.iter():
                if entry.tag.rsplit("}", 1)[-1] not in ("item", "entry"):
                    continue
                fields, link = {}, ""
                for child in entry:
                    tag = child.tag.rsplit("}", 1)[-1]
                    fields[tag] = "".join(child.itertext()).strip()
                    if tag == "link" and child.get("rel", "alternate") == "alternate":
                        link = child.get("href") or fields[tag]
                title = fields.get("title", "")
                summary = " ".join(fields.get(k, "") for k in ("description", "summary", "content"))
                if not any(term in (title + " " + summary).casefold() for term in terms):
                    continue
                link = urljoin(source, link) if link else ""
                if not title or not link or urlsplit(link).scheme not in ("http", "https") or link in seen:
                    continue
                seen.add(link)
                items.append(dict(title=title, link=link,
                                  published=fields.get("pubDate") or fields.get("published") or fields.get("updated") or fields.get("date", ""),
                                  source=source, fetched_at=fetched_at))
        except Exception:
            # 응답·예외에 인증 정보가 들어 있을 수 있으므로 원문은 기록하지 않습니다.
            failures += 1
    status = "failed" if failures == len(sources) else "done"
    return status, items, f"이슈 {len(items)}건, 소스 {len(sources)}개 중 실패 {failures}개."


def fetch_demand(topics: dict, transport: ResearchTransport, *, today: date | None = None) -> tuple[str, list, str]:
    connection = naver_connection()
    if connection is None:
        return "skipped", [], f"NAVER_HUB_CLIENT_ID와 NAVER_HUB_CLIENT_SECRET(권장) 또는 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 환경 변수에 설정하세요. {GUIDE}"
    backend, url, headers = connection
    end = today or date.today()
    start = end - timedelta(weeks=12) + timedelta(days=1)
    keywords = list(dict.fromkeys(topics["seed_keywords"]))[:5]
    payload = {"startDate": start.isoformat(), "endDate": end.isoformat(), "timeUnit": "week",
               "keywordGroups": [{"groupName": k, "keywords": [k]} for k in keywords]}
    headers["User-Agent"] = USER_AGENT
    status, body = transport.request("POST", url, headers, json.dumps(payload).encode("utf-8"))
    if status != 200:
        if status == 401:
            try:
                code = json.loads(body).get("errorCode")
            except (ValueError, AttributeError):
                code = None
            note = (NAVER_MIGRATION_NOTE
                    if backend == "개발자센터" and str(code) == "024" else "네이버 인증 실패 — 앱 Client ID와 Client Secret 확인")
        else:
            note = "네이버 데이터랩 요청 실패 — API 권한·호출 한도·연결을 확인하세요"
        return "failed", [], f"백엔드: {backend}. HTTP {status}: {note}"
    response = json.loads(body)
    items = []
    for result in response["results"]:
        if result["title"] not in keywords:
            continue
        series = result["data"]
        if not isinstance(series, list) or any(
            not isinstance(point, dict) or not isinstance(point.get("period"), str)
            or type(point.get("ratio")) not in (int, float) or not 0 <= point["ratio"] <= 100
            for point in series
        ):
            raise ValueError("데이터랩 상대지수 형식을 확인하세요.")
        if not series:
            continue
        items.append({"keyword": result["title"],
                      "ratio": [{"period": p["period"], "ratio": p["ratio"]} for p in series],
                      "period": {"start": start.isoformat(), "end": end.isoformat()},
                      "unit": "상대지수(0~100)", "source": url, "backend": backend, "fetched_at": timestamp()})
    return "done", items, f"백엔드: {backend}. 검색어 {len(items)}개. 상대지수이며 실제 검색 횟수가 아닙니다."


def run_research(topics: dict | None, out: Path, writer_factory: Callable[[], LLMWriter],
                 transport: ResearchTransport, *, resume: Path | None = None,
                 skip: str | None = None) -> tuple[Path, dict, list]:
    secrets = [os.environ.get(k, "") for k in NAVER_KEY_NAMES]

    def redact(text):
        for secret in secrets:
            if secret:
                text = text.replace(secret, "[비공개]")
        return text

    def clean(value):
        if isinstance(value, str):
            return redact(value)
        if isinstance(value, list):
            return [clean(v) for v in value]
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        return value

    def save(path, value):
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(clean(value), ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8", newline="\n")
        temporary.replace(path)

    if resume:
        run_path = resume.resolve()
        state = json.loads(run_path.read_text(encoding="utf-8"))
        topics = state["topics"]
    else:
        out.mkdir(parents=True, exist_ok=True)
        run_path = out.resolve() / (datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
        # 같은 초에 실행해도 기존 실행을 덮어쓰지 않습니다.
        with run_path.open("x", encoding="utf-8", newline="\n"):
            pass
        state = {"topics": clean(topics), "nodes": {
            node: dict(status="pending", started_at=None, finished_at=None, output_path=None, note="")
            for node in ("N1", "N2", "N3")}}
        save(run_path, state)
    topics = clean(topics)
    outputs = {"N1": [], "N2": [], "N3": []}
    for node, record in state["nodes"].items():
        if record["status"] == "done":
            outputs[node] = json.loads((run_path.parent / record["output_path"]).read_text(encoding="utf-8"))
    for node in ("N1", "N2", "N3"):
        record = state["nodes"][node]
        if record["status"] == "done":
            continue
        record.update(status="pending", started_at=timestamp(), finished_at=None, output_path=None, note="")
        save(run_path, state)
        try:
            if node == skip:
                status, output, note = "skipped", [], "사용자가 --skip N2로 건너뛰었습니다."
            elif node == "N1":
                status, output, note = fetch_issues(topics, transport)
            elif node == "N2":
                status, output, note = fetch_demand(topics, transport)
            else:
                writer = writer_factory()
                reply = writer.write(topic_prompt(topics, outputs["N1"], outputs["N2"]), str(run_path.parent))
                output = validate_candidates(redact(reply), topics, outputs["N1"], outputs["N2"])
                status = "done" if output else "failed"
                note = f"G1 사람 승인 대기: 후보 {len(output)}개." if output else "검증을 통과한 후보가 없습니다. 근거·제외 주제를 확인하세요."
                run_path.with_suffix(".topics.md").write_text(render_topics(output), encoding="utf-8", newline="\n")
            output = clean(output)
            if status == "done":
                path = run_path.with_suffix(f".{node}.json")
                save(path, output)
                record["output_path"] = path.name
            outputs[node] = output
            record.update(status=status, note=note)
        except Exception:
            record.update(status="failed", note=(
                "AI 엔진 실행 또는 JSON 검증 실패 — Claude Code/Codex CLI 설치·로그인과 응답을 확인하세요."
                if node == "N3" else "자료 요청 또는 응답 처리 실패 — 연결과 자료 형식을 확인하세요."))
        if node == "N2" and record["status"] != "skipped" and "백엔드:" not in record["note"]:
            connection = naver_connection()
            if connection is not None:
                record["note"] = f"백엔드: {connection[0]}. " + record["note"]
        record["finished_at"] = timestamp()
        save(run_path, state)
    return run_path, clean(state), outputs["N3"]
