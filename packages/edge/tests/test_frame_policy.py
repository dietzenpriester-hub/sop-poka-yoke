"""按步骤类型分流的帧策略测试。"""

import numpy as np

from src.inference.frame_policy import (
    is_release_step,
    is_transition_step,
    select_frames_for_step,
    uses_temporal_window,
)


def _frame(value: int) -> np.ndarray:
    return np.full((4, 4, 3), value, dtype=np.uint8)


def test_release_aliases_are_recognized():
    for kind in ("place", "Put", "PUT_DOWN", "drop", "release", "unload"):
        assert is_release_step(kind)
    for kind in ("pick", "inspect", "hold", "standby", "screw", "", None):
        assert not is_release_step(kind)


def test_transition_aliases_are_recognized():
    for kind in ("pick", "Pickup", "TAKE", "grab", "pick_place"):
        assert is_transition_step(kind)
    for kind in ("place", "inspect", "hold", "standby", "", None):
        assert not is_transition_step(kind)


def test_place_step_uses_current_frame_not_stale_window():
    sequence = [_frame(1), _frame(2), _frame(3), _frame(4)]
    current = _frame(99)

    selected = select_frames_for_step("place", sequence, current)

    assert len(selected) == 1
    assert int(selected[0][0, 0, 0]) == 99


def test_pick_step_uses_current_frame_not_stale_window():
    sequence = [_frame(1), _frame(2), _frame(3), _frame(4)]
    current = _frame(99)

    selected = select_frames_for_step("pick", sequence, current)

    assert len(selected) == 1
    assert int(selected[0][0, 0, 0]) == 99


def test_empty_sequence_falls_back_to_current_frame():
    current = _frame(7)

    assert len(select_frames_for_step("pick", [], current)) == 1
    assert int(select_frames_for_step("pick", [], current)[0][0, 0, 0]) == 7


def test_adaptive_off_keeps_window_for_place(monkeypatch):
    monkeypatch.setenv("SOP_VLM_ADAPTIVE_WINDOW", "0")
    sequence = [_frame(1), _frame(2)]

    assert uses_temporal_window("place") is True
    assert len(select_frames_for_step("place", sequence, _frame(9))) == 2


def test_adaptive_flag_overrides_env(monkeypatch):
    monkeypatch.setenv("SOP_VLM_ADAPTIVE_WINDOW", "0")

    assert uses_temporal_window("place", adaptive=True) is False
    assert len(select_frames_for_step("place", [_frame(1), _frame(2)], _frame(9), adaptive=True)) == 1


def test_env_default_is_adaptive(monkeypatch):
    monkeypatch.delenv("SOP_VLM_ADAPTIVE_WINDOW", raising=False)

    assert uses_temporal_window("place") is False
    assert uses_temporal_window("pick") is False
    assert uses_temporal_window("inspect") is True
