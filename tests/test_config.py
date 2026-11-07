from pathlib import Path
import re

import pytest

from frame.config_loader import load_graph, load_pack, load_profile
from frame.core.models import GateLevel

ROOT = Path(__file__).resolve().parents[1]


def test_profile_and_all_patterns():
    spec, persona, names, video = load_profile(ROOT / "config/profile.example.toml")
    assert (spec.min_chars, spec.max_chars, spec.headings) == (1200, 1800, 3)
    assert persona["region"] == "울산"
    assert video == {"target_seconds": 45, "tolerance_seconds": 5}
    assert names == ["general_ko", "medical_ko"]
    re.compile(spec.human_slot_pattern)
    for name in names:
        pack = load_pack(name, ROOT / "config/rules")
        assert pack.rules
        for rule in pack.rules:
            re.compile(rule.pattern)
            assert rule.severity in ("warn", "error")


def test_graph_edges_and_human_only():
    nodes, edges, gates = load_graph(ROOT / "config/graph.toml")
    assert len(nodes) == 11
    assert len(gates) == 5
    ids = {node["id"] for node in nodes} | {gate.id for gate in gates}
    assert all(edge[side] in ids for edge in edges for side in ("source", "target"))
    assert all(g.start == g.max == GateLevel.HUMAN_ONLY for g in gates if g.id in ("G3", "G5"))
    assert any(e["source"] == "N6" and e["target"] == "N5" and e["max_loops"] == 2 for e in edges)


def test_default_profile_fallback_and_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    content = (ROOT / "config/profile.example.toml").read_text(encoding="utf-8")
    (config / "profile.example.toml").write_text(content, encoding="utf-8")
    assert load_profile()[1]["region"] == "울산"
    (config / "profile.toml").write_text(content.replace('region = "울산"', 'region = "부산"'), encoding="utf-8")
    assert load_profile()[1]["region"] == "부산"


def test_pack_name_cannot_escape_rules_directory():
    with pytest.raises(ValueError):
        load_pack("../profile.example")
