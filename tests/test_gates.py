from dataclasses import replace

import pytest

from frame.core.gates import needs_human_review, next_level, replay
from frame.core.models import Decision, GateDecision, GateLevel, GateSpec

SPEC = GateSpec("G1", "주제 승인", GateLevel.L0, GateLevel.L2, "주제를 사람이 확인합니다.")


def history(count, *, gate="G1"):
    return [GateDecision(gate, str(i), Decision.APPROVED, False, "", f"2026-01-01T00:00:{i:02d}+00:00") for i in range(count)]


def test_promote_nine_of_ten_and_cap():
    records = history(10)
    records[0] = replace(records[0], decision=Decision.EDITED)
    assert next_level(records[:9], SPEC, GateLevel.L0) == GateLevel.L0
    assert next_level(records, SPEC, GateLevel.L0) == GateLevel.L1
    assert next_level(records, SPEC, GateLevel.L1) == GateLevel.L2
    assert next_level(records, SPEC, GateLevel.L2) == GateLevel.L2
    assert next_level(records, replace(SPEC, max=GateLevel.L1), GateLevel.L1) == GateLevel.L1
    records[1] = replace(records[1], decision=Decision.REJECTED)
    assert next_level(records, SPEC, GateLevel.L0) == GateLevel.L0


def test_demotion_discards_previous_window():
    records = history(21)
    records[10] = replace(records[10], missed_by_machine=True)
    assert next_level(records[:11], SPEC, GateLevel.L2) == GateLevel.L0
    assert replay(records[:11], SPEC) == GateLevel.L0
    assert replay(records[:20], SPEC) == GateLevel.L0
    assert replay(records, SPEC) == GateLevel.L1


def test_human_only_never_changes():
    spec = replace(SPEC, start=GateLevel.HUMAN_ONLY, max=GateLevel.HUMAN_ONLY)
    records = history(12)
    assert replay(records, spec) == GateLevel.HUMAN_ONLY
    records[-1] = replace(records[-1], missed_by_machine=True)
    assert next_level(records, spec, GateLevel.HUMAN_ONLY) == GateLevel.HUMAN_ONLY


def test_replay_is_chronological_and_gate_specific():
    assert replay(list(reversed(history(11))) + history(20, gate="G2"), SPEC) == GateLevel.L2
    assert replay(history(20, gate="G2"), SPEC) == GateLevel.L0


@pytest.mark.parametrize("index,expected", [(1, False), (2, False), (3, True), (4, False), (6, True)])
def test_l1_every_third(index, expected):
    assert needs_human_review(GateLevel.L1, index) == expected
    assert needs_human_review(GateLevel.L0, index)
    assert needs_human_review(GateLevel.HUMAN_ONLY, index)
    assert not needs_human_review(GateLevel.L2, index)
