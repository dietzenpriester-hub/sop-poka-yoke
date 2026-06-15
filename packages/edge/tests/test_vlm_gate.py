"""VLM 触发门控测试。"""

import pytest

from src.engine.vlm_gate import VLMGateConfig, VLMTriggerGate, _parse_roi


def _det(label: str = "person", conf: float = 0.8, bbox=(40, 40, 80, 80)) -> dict:
    return {"class_name": label, "confidence": conf, "bbox": bbox}


def test_gate_requires_stable_hits():
    gate = VLMTriggerGate(VLMGateConfig(stable_frames=2, cooldown_seconds=0.0))
    first = gate.should_submit([_det()], (100, 100, 3), now=1.0)
    second = gate.should_submit([_det()], (100, 100, 3), now=2.0)

    assert not first.allowed
    assert first.reason == "warming"
    assert second.allowed
    assert second.reason == "stable"


def test_gate_resets_when_detection_missing():
    gate = VLMTriggerGate(VLMGateConfig(stable_frames=2, cooldown_seconds=0.0))
    gate.should_submit([_det()], (100, 100, 3), now=1.0)
    miss = gate.should_submit([], (100, 100, 3), now=2.0)
    next_hit = gate.should_submit([_det()], (100, 100, 3), now=3.0)

    assert miss.reason == "no_relevant_detection"
    assert miss.stable_hits == 0
    assert not next_hit.allowed
    assert next_hit.stable_hits == 1


def test_gate_filters_by_roi_and_target():
    gate = VLMTriggerGate(
        VLMGateConfig(
            roi=(0.0, 0.0, 0.5, 0.5),
            stable_frames=1,
            cooldown_seconds=0.0,
            target_objects={"person"},
        )
    )

    outside = gate.should_submit([_det(bbox=(70, 70, 90, 90))], (100, 100, 3), now=1.0)
    wrong_label = gate.should_submit([_det(label="chair", bbox=(10, 10, 30, 30))], (100, 100, 3), now=2.0)
    inside = gate.should_submit([_det(bbox=(10, 10, 30, 30))], (100, 100, 3), now=3.0)

    assert outside.reason == "no_relevant_detection"
    assert wrong_label.reason == "no_relevant_detection"
    assert inside.allowed


def test_gate_cooldown_blocks_fast_retrigger():
    gate = VLMTriggerGate(VLMGateConfig(stable_frames=1, cooldown_seconds=2.0))
    allowed = gate.should_submit([_det()], (100, 100, 3), now=10.0)
    blocked = gate.should_submit([_det()], (100, 100, 3), now=11.0)
    later = gate.should_submit([_det()], (100, 100, 3), now=12.1)

    assert allowed.allowed
    assert blocked.reason == "cooldown"
    assert later.allowed


def test_parse_roi_validation():
    assert _parse_roi("0.1,0.2,0.8,0.9") == (0.1, 0.2, 0.8, 0.9)
    with pytest.raises(ValueError):
        _parse_roi("0.5,0.5,0.1,0.9")
