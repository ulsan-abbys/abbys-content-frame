"""설정·순수 도메인·입출력 포트를 연결하는 얇은 명령행 진입점."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from frame.adapters.claude_cli import ClaudeCliWriter
from frame.adapters.codex_cli import CodexCliWriter, CodexCliJudge
from frame.adapters.engines import EngineUnavailable, select_engine
from frame.adapters.new_workspace import create_workspace
from frame.adapters.setup import ask_topics, doctor, save_topics
from frame.adapters.research import HttpResearchTransport, run_research
from frame.core.ports import ResearchTransport
from frame.config_loader import load_topics
from frame.core.ports import NaverTransport
from frame.adapters.claude_judge import ClaudeCliJudge
from frame.adapters.page_http import HttpPageFetcher
from frame.adapters.jsonl_log import JsonlGateLog
from frame.adapters.mpt_cli import MoneyPrinterTurboRenderer
from frame.config_loader import load_graph, load_pack, load_profile, load_writing_profile, resolve_profile
from frame.core.checks import run_checks
from frame.core.gates import needs_human_review, replay
from frame.core.models import Decision, GateDecision, GateLevel
from frame.adapters.write_workspace import WriteWorkspace
from frame.core.pipeline import run_write_loop
from frame.core.ports import GateLog, LLMWriter, PageFetcher, SourceJudge, VideoRenderer
from frame.core.scoring import parse_draft, score_sources
from frame.core.naver import count_naver_body, markdown_to_naver
from frame.core.naver_capture import CAPTURE_SCRIPT
from frame.core.naver_check import check_naver
from frame.config_loader import load_experience_label
from frame.adapters.naver_html import save_agent_instructions, save_naver_html


class KoreanParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)
        self.add_argument("-h", "--help", action="help", help="도움말을 표시합니다.")
        self._positionals.title = "위치 인자"
        self._optionals.title = "선택 인자"

    def format_usage(self):
        return super().format_usage().replace("usage:", "사용법:", 1)

    def format_help(self):
        return super().format_help().replace("usage:", "사용법:", 1)

    def error(self, message):
        self.print_usage()
        self.exit(2, "오류: 명령 인자가 올바르지 않습니다. --help로 필수 인자와 허용 값을 확인하세요.\n")


def build_parser() -> argparse.ArgumentParser:
    parser = KoreanParser(prog="frame", description="블로그 초안과 영상 작업을 점검하는 공동 작업 틀")
    commands = parser.add_subparsers(dest="command", required=True, title="명령")
    research = commands.add_parser("research", help="N1~N3 사전 조사 후 G1 주제 후보를 저장합니다.")
    research.add_argument("--profile", metavar="설정", help="주제 프로필 (기본: config/profile.toml)")
    research.add_argument("--engine", choices=("auto", "claude", "codex"), default="auto", help="후보 생성 엔진")
    research.add_argument("--out", default="runs", metavar="폴더", help="조사 결과 폴더")
    research.add_argument("--resume", metavar="실행파일", help="완료 노드를 건너뛰고 저장된 조사 재개")
    research.add_argument("--skip", choices=("N2",), help="검색 수요 노드를 건너뜁니다.")
    setup = commands.add_parser("setup", help="블로그 주제와 API 준비 상태를 설정·점검합니다.")
    setup_commands = setup.add_subparsers(dest="setup_command", required=True, title="설정 명령")
    topics = setup_commands.add_parser("topics", help="내 블로그의 분야·독자·검색어를 저장합니다.")
    topics.add_argument("--from-json", metavar="파일", help="질문 대신 JSON 파일에서 주제 설정을 읽습니다.")
    diagnostic = setup_commands.add_parser("doctor", help="엔진·주제·API 키의 준비 상태를 확인합니다.")
    diagnostic.add_argument("--check-naver", action="store_true", help="네이버 데이터랩에 실제 요청을 한 번 보냅니다.")
    for sub in (topics, diagnostic):
        sub.add_argument("--profile", metavar="설정", help="프로필 TOML 경로 (기본: config/profile.toml)")
    check = commands.add_parser("check", help="초안의 분량과 표현을 점검합니다.")
    check.add_argument("md", metavar="초안", help="마크다운 파일 경로")
    check.add_argument("--profile", metavar="설정", help="프로필 TOML 경로")
    score = commands.add_parser("score", help="출처와 초안 주제의 대응을 채점합니다.")
    score.add_argument("md", metavar="초안", help="마크다운 파일 경로")
    score.add_argument("--profile", metavar="설정", help="프로필 TOML 경로")
    gate = commands.add_parser("gate", help="사람 검수 기록과 자동화 단계를 확인합니다.")
    gate.add_argument("--log", default="logs/gates.jsonl", metavar="로그", help="관문 로그 경로")
    gate_commands = gate.add_subparsers(dest="gate_command", required=True, title="관문 명령")
    record = gate_commands.add_parser("record", help="검수 결과를 기록합니다.")
    status = gate_commands.add_parser("status", help="관문별 현재 단계를 표시합니다.")
    for sub in (record, status):
        sub.add_argument("--log", default=argparse.SUPPRESS, metavar="로그", help="관문 로그 경로")
    record.add_argument("--gate", required=True, metavar="관문", help="관문 ID (예: G2)")
    record.add_argument("--decision", choices=[d.value for d in Decision], required=True,
                        help="approved: 승인, edited: 수정, rejected: 반려")
    record.add_argument("--missed-by-machine", action="store_true", help="기계가 놓친 문제를 사람이 발견했습니다.")
    record.add_argument("--note", default="", metavar="메모", help="검수 메모")
    record.add_argument("--run-id", metavar="실행번호", help="기본값은 현재 시각입니다.")
    commands.add_parser("graph", help="노드·연결·사람 관문을 표시합니다.")
    write = commands.add_parser("write", help="선택한 AI CLI로 현재 작업을 이어갑니다.")
    write.add_argument("workdir", metavar="작업폴더", help="STATE.md가 있는 작업 폴더")
    write.add_argument("--topic", metavar="주제", help="프로필의 글 종류로 새 초안을 작성하고 점검합니다.")
    write.add_argument("--draft", metavar="상대경로", help="작업 폴더 기준 초안 경로")
    write.add_argument("--max-rewrites", type=int, default=2, metavar="횟수", help="최대 고쳐 쓰기 횟수")
    write.add_argument("--profile", metavar="설정", help="프로필 TOML 경로")
    for command in (write, score):
        command.add_argument("--engine", choices=("auto", "claude", "codex"),
                             help="AI 엔진 (기본: FRAME_ENGINE 또는 auto, codex → claude 순)")
    new = commands.add_parser("new", help="일반 블로그 작업 폴더를 만듭니다.")
    new.add_argument("workdir", metavar="폴더", help="새로 만들 작업 폴더")
    new.add_argument("--field", default="생활", help="글의 분야")
    new.add_argument("--name", default="가상의 생활 블로거", help="화자 이름")
    new.add_argument("--region", default="울산", help="독자 지역")
    render = commands.add_parser("render", help="대본으로 세로 영상을 만듭니다.")
    render.add_argument("script", metavar="대본", help="UTF-8 대본 파일")
    render.add_argument("--out", required=True, metavar="출력폴더", help="완성 영상을 복사할 폴더")
    naver = commands.add_parser("naver", help="네이버에 붙여넣을 HTML을 만듭니다.")
    naver_commands = naver.add_subparsers(dest="naver_command", required=True, title="네이버 명령")
    draft = naver_commands.add_parser("draft", help="초안 한 개를 HTML로 변환합니다.")
    draft.add_argument("md", metavar="초안.md", help="변환할 마크다운 파일")
    draft.add_argument("--editor-url", metavar="URL", help="연습용 편집기 URL (생략하면 네이버 블로그)")
    naver_commands.add_parser("capture-script", help="읽기 전용 수집 코드를 출력합니다.")
    capture_check = naver_commands.add_parser("check", help="임시저장 캡처를 원고와 대조합니다.")
    capture_check.add_argument("md", metavar="초안.md", help="기대값을 생성할 원고")
    capture_check.add_argument("capture", metavar="capture.json", help="수집 JSON 파일")
    capture_check.add_argument("--stage", choices=("draft", "publish"), default="draft", help="점검 단계")
    capture_check.add_argument("--json", action="store_true", help="판정 JSON 출력")
    for sub in (draft, capture_check):
        sub.add_argument("--label", help="경험 라벨 (기본: 작업 폴더 설정 또는 내 경험)")
    return parser


def main(argv: list[str] | None = None, *, writer: LLMWriter | None = None,
         renderer: VideoRenderer | None = None, gate_log: GateLog | None = None,
         fetcher: PageFetcher | None = None, judge: SourceJudge | None = None,
         naver_transport: NaverTransport | None = None,
         research_transport: ResearchTransport | None = None,
         config_dir: str | Path = "config") -> int:
    # Korean Windows consoles are cp949; page quotes may hold characters it cannot encode.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    if args.command == "naver" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    config_dir = Path(config_dir)
    try:
        if args.command == "research":
            def research_writer():
                if writer is not None:
                    return writer
                engine = select_engine(args.engine)
                return CodexCliWriter() if engine == "codex" else ClaudeCliWriter(allowed_tools=())

            try:
                topics = None if args.resume else load_topics(Path(args.profile) if args.profile else config_dir / "profile.toml")
                path, state, candidates = run_research(
                    topics, Path(args.out), research_writer,
                    research_transport if research_transport is not None else HttpResearchTransport(),
                    resume=Path(args.resume) if args.resume else None, skip=args.skip)
            except (OSError, ValueError, KeyError, TypeError):
                print("조사를 시작할 수 없습니다. frame setup topics 설정 또는 재개 파일·결과 경로를 확인하세요.")
                return 1
            print(f"조사 기록: {path}")
            for node, record in state["nodes"].items():
                print(f"{node}: {record['status']} — {record['note']}")
            if candidates:
                print(f"G1 검토 문서: {path.with_suffix('.topics.md')}")
                print("사람이 주제를 승인한 뒤 실행하세요 (마지막 .은 작업 폴더로 바꾸세요):")
                title = candidates[0]["title"].replace('"', '').replace('\n', ' ').replace('\r', ' ')
                print(f'frame write --topic "{title}" .')
            return 1 if any(r["status"] == "failed" for r in state["nodes"].values()) else 0
        if args.command == "setup":
            path = Path(args.profile) if args.profile else config_dir / "profile.toml"
            if args.setup_command == "doctor":
                return doctor(path, check_naver=args.check_naver, transport=naver_transport)
            try:
                data = json.loads(Path(args.from_json).read_text(encoding="utf-8-sig")) if args.from_json else ask_topics()
                save_topics(path, data, template=config_dir / "profile.example.toml")
            except (EOFError, KeyboardInterrupt):
                print("설정을 취소했습니다. 파일은 바꾸지 않았습니다.")
                return 1
            print(f"블로그 주제 설정을 저장했습니다: {path}")
            return 0
        if args.command == "naver":
            if args.naver_command == "capture-script":
                print(CAPTURE_SCRIPT)
                return 0
            path = Path(args.md)
            label = args.label if args.label is not None else load_experience_label(path)
            if args.naver_command == "check":
                capture = json.loads(Path(args.capture).read_text(encoding="utf-8-sig"))
                if isinstance(capture, str):
                    capture = json.loads(capture)
                result = check_naver(path.read_text(encoding="utf-8-sig"), capture, label, args.stage)
                if args.json:
                    print(json.dumps(result, ensure_ascii=False))
                else:
                    icons = {"PASS": "✅", "WARN": "⚠", "FAIL": "❌"}
                    for item in result["items"]:
                        print(f"{icons[item['status']]} {item['code']} {item['message']}")
                    counts = result["counts"]
                    summary = " · ".join(f"{name} {counts[key]['matched']}/{counts[key]['total']}"
                                         for key, name in (("headings", "소제목"), ("items", "목록"),
                                                           ("bolds", "굵게"), ("links", "링크")))
                    print(f"판정: {result['verdict']} — {summary}")
                return 1 if result["verdict"] == "FAIL" else 0
            draft = markdown_to_naver(path.read_text(encoding="utf-8-sig"), label)
            html_path = save_naver_html(path, draft)
            print(f"[HTML 변환] 저장: {html_path}")
            print(f"[실행 지시서] 저장: {save_agent_instructions(path, draft, html_path, args.editor_url)}")
            print(count_naver_body(draft.html).confirmation())
            if draft.has_experience_slots:
                print("경고: 경험 슬롯이 남아 있습니다. 발행 전에 직접 채우세요.")
            if not draft.title or not draft.plain.strip():
                raise ValueError("초안에 '# 제목'과 비어 있지 않은 본문이 필요합니다.")
            print("HTML 파일 열기 → [본문 복사] → 편집기 본문 클릭 → Ctrl+V → [제목 복사] → 제목 칸 클릭 → Ctrl+V → 서식 확인 → 임시저장; 공개 발행을 명시 승인한 글은 실행 지시서의 조건에 따라 발행·게시물 URL 확인까지")
            return 0
        if args.command == "new":
            create_workspace(args.workdir, config_dir / "profile.example.toml",
                             field=args.field, name=args.name, region=args.region)
            print(f"작업 폴더 생성: {args.workdir}")
            return 0
        engine = None
        if args.command in ("write", "score"):
            needs_engine = (judge is None if args.command == "score" else
                            writer is None or (args.topic is not None and judge is None))
            if needs_engine:
                engine = select_engine(args.engine)
            print(f"엔진: {engine or '주입된 구현'}")
        writer_type = CodexCliWriter if engine == "codex" else ClaudeCliWriter
        judge_type = CodexCliJudge if engine == "codex" else ClaudeCliJudge
        if args.command in ("check", "score"):
            profile = resolve_profile(args.profile, config_dir)
            spec, _, names, _ = load_profile(profile)
            if args.command == "score":
                parsed = parse_draft(Path(args.md).read_text(encoding="utf-8-sig"))
                page_fetcher = fetcher if fetcher is not None else HttpPageFetcher()
                source_judge = judge if judge is not None else judge_type()
                score_result = score_sources(parsed, page_fetcher.fetch, source_judge.judge, spec.min_sources)
                for verdict in score_result.verdicts:
                    print(f"[{verdict.verdict}] {verdict.label} - {verdict.reason}")
                    if verdict.evidence:
                        print(f"근거: {verdict.evidence}")
                print(f"출처 대응 {score_result.supported}/{score_result.required}")
                print("채점 통과" if score_result.passed else "채점 실패")
                return 0 if score_result.passed else 1
            packs = [load_pack(name, config_dir / "rules") for name in names]
            result = run_checks(Path(args.md).read_text(encoding="utf-8-sig"), spec, packs)
            print("항목 | 측정값")
            labels = {"chars": "본문 글자 수(공백 제외)", "headings": "본문 소제목 수",
                      "sources": "출처 URL 줄 수", "human_slots": "사람 경험 입력 자리 수"}
            for key, value in result.metrics.items():
                print(f"{labels[key]} | {value}")
            for finding in result.findings:
                severity = "오류" if finding.severity == "error" else "경고"
                location = f"{finding.line}줄" if finding.line is not None else "문서 전체"
                print(f"[{severity}] {finding.rule_id} ({location}): {finding.message}")
            print("점검 통과" if result.passed else "점검 실패")
            return 0 if result.passed else 1
        if args.command == "write":
            draft_writer = writer if writer is not None else (
                writer_type(allow_edits=True) if args.topic is None else writer_type())
            if args.topic is None:
                print(draft_writer.write("STATE.md 보고 지금 하는 일을 이어서 해줘.", args.workdir))
                return 0
            if not args.topic.strip():
                raise ValueError("주제를 입력하세요.")
            workspace = WriteWorkspace(args.workdir, args.topic, args.draft)
            profile = resolve_profile(args.profile, config_dir, args.workdir)
            spec, _, names, _ = load_profile(profile)
            packs = [load_pack(name, config_dir / "rules") for name in names]
            page_fetcher = fetcher if fetcher is not None else HttpPageFetcher()
            source_judge = judge if judge is not None else judge_type()

            def check_draft(text):
                result = run_checks(text, spec, packs)
                lines = []
                for finding in result.findings:
                    severity = "오류" if finding.severity == "error" else "경고"
                    location = f"{finding.line}줄" if finding.line is not None else "문서 전체"
                    lines.append(f"[{severity}] {finding.rule_id} ({location}): {finding.message}")
                return result.passed, result.metrics, lines

            def score_draft(text):
                result = score_sources(parse_draft(text), page_fetcher.fetch,
                                       source_judge.judge, spec.min_sources)
                lines = []
                for verdict in result.verdicts:
                    lines.append(f"[{verdict.verdict}] {verdict.label} - {verdict.reason}")
                    if verdict.evidence:
                        lines.append(f"근거: {verdict.evidence}")
                lines.append(f"출처 대응 {result.supported}/{result.required}")
                return result.passed, result.supported, result.required, lines

            def log_round(record):
                workspace.log(record)
                status = "통과" if record.check_passed else "실패"
                print(f"[라운드 {record.round}] 점검 {status} · 출처 대응 "
                      f"{record.supported}/{record.required} · 초 {record.seconds:.1f}")
                if not (record.check_passed and record.score_passed):
                    for line in record.findings + record.verdict_lines:
                        print(line)

            outcome = run_write_loop(
                args.topic, workspace.draft_rel,
                lambda prompt: workspace.save_reply(draft_writer.write(prompt, args.workdir)), workspace.save_draft,
                check_draft, score_draft, log_round, args.max_rewrites, clock=time.monotonic,
                profile=load_writing_profile(profile),
                agents_text=workspace.read_agents(),
                profile_text=profile.read_text(encoding="utf-8-sig"),
            )
            workspace.append_state(outcome.passed, outcome.rounds[-1].round)
            if outcome.draft_missing:
                print(f"초안 파일이 없습니다. 사람이 확인하세요: {workspace.draft_rel}")
                return 1
            if outcome.passed:
                print(f"기계 점검 통과 - 사람 검수 대기 (G2): {workspace.draft_rel}")
                return 0
            print(f"기계 점검 실패 (최대 고쳐 쓰기 {args.max_rewrites}회) - "
                  f"사람이 확인하세요: {workspace.draft_rel}")
            return 1
        if args.command == "render":
            script = Path(args.script).read_text(encoding="utf-8-sig")
            path = (renderer if renderer is not None else MoneyPrinterTurboRenderer()).render(script, args.out)
            print(f"영상 생성 완료: {path}")
            return 0
        nodes, edges, gates = load_graph(config_dir / "graph.toml")
        if args.command == "graph":
            print("작업 노드")
            for node in nodes:
                print(f"  {node['id']} {node['name']} (자동 단계)")
            print("연결")
            for edge in edges:
                suffix = ""
                if edge.get("condition"):
                    suffix = " (실패)" if edge["condition"] == "fail" else " (통과)"
                if "max_loops" in edge:
                    suffix += f" 최대 {edge['max_loops']}회 되돌림"
                print(f"  {edge['source']} → {edge['target']}{suffix}")
            print("사람 관문")
            for gate in gates:
                level = "항상 사람" if gate.start == GateLevel.HUMAN_ONLY else f"{gate.start.value} → 최대 {gate.max.value}"
                print(f"  {gate.id} {gate.name}: {level}\n    이유: {gate.why}")
            return 0
        log = gate_log if gate_log is not None else JsonlGateLog(args.log)
        if args.gate_command == "record":
            if args.gate not in {gate.id for gate in gates}:
                raise ValueError(f"정의되지 않은 관문입니다: {args.gate}")
            ts = datetime.now(timezone.utc).isoformat()
            log.append(GateDecision(args.gate, args.run_id or ts, Decision(args.decision),
                                    args.missed_by_machine, args.note, ts))
            print(f"{args.gate} 검수 기록을 저장했습니다.")
        else:
            history = log.read()
            for gate in gates:
                relevant = sorted((d for d in history if d.gate == gate.id), key=lambda d: d.ts)
                level = replay(relevant, gate)
                recent = relevant[-10:]
                summary = ", ".join(f"{label} {sum(d.decision == decision for d in recent)}"
                                    for decision, label in [(Decision.APPROVED, "승인"),
                                                            (Decision.EDITED, "수정"), (Decision.REJECTED, "반려")])
                missed = sum(d.missed_by_machine for d in recent)
                review = "사람 검토 필요" if needs_human_review(level, len(relevant) + 1) else "사람 검토 생략 가능"
                print(f"{gate.id} {gate.name} | {level.value} | 최근 {len(recent)}건: {summary}, 기계 누락 {missed} | 다음 실행: {review}")
        return 0
    except EngineUnavailable as exc:
        print(f"오류: 작업을 완료할 수 없습니다. {exc}")
        return 2
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        message = "작업을 진행할 수 없습니다." if args.command == "write" else "작업을 완료할 수 없습니다."
        print(f"오류: {message} {exc}")
        return 2 if args.command == "score" or (args.command == "naver" and args.naver_command == "check") else 1
