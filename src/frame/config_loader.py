"""TOML 설정을 읽고 도메인 값 객체로 변환하는 조립 경계."""

from pathlib import Path
import re
import tomllib

from frame.core.models import DraftSpec, GateLevel, GateSpec, Rule, RulePack
from frame.core.pipeline import WritingProfile
from frame.core.naver import NaverSetupRequired


def load_naver_settings(draft_path: Path, explicit_id: str | None) -> tuple[str, str]:
    """초안에서 가장 가까운 상위 작업폴더 설정을 사용합니다."""
    profile = next((parent / "profile.toml" for parent in draft_path.resolve().parents
                    if (parent / "profile.toml").is_file()), None)
    data = _read(profile) if profile else {}
    blog_id = explicit_id if explicit_id is not None else data.get("naver", {}).get("blog_id", "")
    label = data.get("writing", {}).get("experience_label", "내 경험")
    if not isinstance(blog_id, str) or not isinstance(label, str):
        raise NaverSetupRequired("blog_id와 experience_label은 문자열이어야 합니다.")
    return blog_id.strip(), label


def validate_naver_blog_id(blog_id: str) -> None:
    if not blog_id:
        raise NaverSetupRequired("--blog-id ID 또는 작업폴더/profile.toml의 [naver] blog_id를 설정하세요.")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", blog_id):
        raise NaverSetupRequired("blog_id에는 블로그 주소 전체가 아닌 영문·숫자·밑줄·하이픈 ID를 입력하세요.")


def _read(path: str | Path) -> dict:
    with Path(path).open("rb") as stream:
        return tomllib.load(stream)


def load_profile(path: str | Path | None = None) -> tuple[DraftSpec, dict, list[str], dict]:
    if path is None:
        custom = Path("config/profile.toml")
        path = custom if custom.exists() else Path("config/profile.example.toml")
    data = _read(path)
    draft = dict(data["draft"])
    label = data.get("writing", {}).get("experience_label", "내 경험")
    draft.setdefault("human_slot_pattern", r"\[" + re.escape(label))
    spec = DraftSpec(**draft)
    if not 0 <= spec.min_chars <= spec.max_chars:
        raise ValueError("글자 수의 최솟값과 최댓값을 확인하세요.")
    if min(spec.headings, spec.min_sources, spec.min_human_slots) < 0:
        raise ValueError("점검 개수 기준은 음수일 수 없습니다.")
    re.compile(spec.human_slot_pattern)
    return spec, data["persona"], data["rules"]["packs"], data["video"]


def load_writing_profile(path: str | Path) -> WritingProfile:
    data = _read(path)
    return WritingProfile(**data.get("writing", {}), persona=data.get("persona", {}),
                          style=data.get("style", {}))


def resolve_profile(explicit: str | None, config_dir: Path, workdir: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    candidates = ([Path(workdir) / "profile.toml"] if workdir is not None else [])
    candidates += [config_dir / "profile.toml", config_dir / "profile.example.toml"]
    return next((path for path in candidates if path.is_file()), candidates[-1])


def load_pack(name: str, rules_dir: str | Path = "config/rules") -> RulePack:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError("규칙 팩 이름은 영문, 숫자, 밑줄, 하이픈만 사용할 수 있습니다.")
    rules = [Rule(**data) for data in _read(Path(rules_dir) / f"{name}.toml")["rule"]]
    for rule in rules:
        re.compile(rule.pattern)
        if rule.severity not in ("error", "warn"):
            raise ValueError(f"규칙 {rule.id}의 심각도는 error 또는 warn이어야 합니다.")
    return RulePack(name, rules)


def load_graph(path: str | Path = "config/graph.toml") -> tuple[list[dict], list[dict], list[GateSpec]]:
    data = _read(path)
    gates = [GateSpec(**{**gate, "start": GateLevel(gate["start"]), "max": GateLevel(gate["max"])})
             for gate in data["gates"]]
    nodes, edges = data["nodes"], data["edges"]
    identifiers = [node["id"] for node in nodes] + [gate.id for gate in gates]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("그래프의 노드와 관문 ID는 중복될 수 없습니다.")
    for edge in edges:
        if edge["source"] not in identifiers or edge["target"] not in identifiers:
            raise ValueError("그래프 연결에 정의되지 않은 노드 또는 관문이 있습니다.")
    for gate in gates:
        if gate.id in ("G3", "G5") and (gate.start != GateLevel.HUMAN_ONLY or gate.max != GateLevel.HUMAN_ONLY):
            raise ValueError("게시·업로드 클릭 관문은 항상 사람이 수행해야 합니다.")
        if GateLevel.HUMAN_ONLY in (gate.start, gate.max):
            if gate.start != gate.max:
                raise ValueError("사람 전용 관문의 시작과 최대 단계는 같아야 합니다.")
        elif gate.start.value > gate.max.value:
            raise ValueError("관문 시작 단계는 최대 단계보다 높을 수 없습니다.")
    return nodes, edges, gates
