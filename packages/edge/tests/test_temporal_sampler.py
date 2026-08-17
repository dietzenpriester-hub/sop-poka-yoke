"""时序帧采样器测试。"""

import numpy as np
import pytest

from src.capture.temporal_sampler import TemporalFrameSampler


def _frame(value: int) -> np.ndarray:
    return np.full((8, 8, 3), value, dtype=np.uint8)


def test_rejects_frames_inside_interval():
    sampler = TemporalFrameSampler(window=4, interval_seconds=0.4)

    assert sampler.offer(_frame(1), 0.0) is True
    assert sampler.offer(_frame(2), 0.2) is False
    assert sampler.offer(_frame(3), 0.4) is True
    assert len(sampler) == 2


def test_window_keeps_newest_frames_in_time_order():
    sampler = TemporalFrameSampler(window=3, interval_seconds=0.4)
    for i in range(5):
        sampler.offer(_frame(i), i * 0.4)

    snapshot = sampler.snapshot()

    assert len(snapshot) == 3
    assert [int(f[0, 0, 0]) for f in snapshot] == [2, 3, 4]


def test_span_reflects_configured_interval():
    sampler = TemporalFrameSampler(window=4, interval_seconds=0.5)
    for i in range(4):
        sampler.offer(_frame(i), i * 0.5)

    assert sampler.span_seconds() == pytest.approx(1.5)


def test_span_is_zero_before_second_frame():
    sampler = TemporalFrameSampler()

    assert sampler.span_seconds() == 0.0
    sampler.offer(_frame(1), 0.0)
    assert sampler.span_seconds() == 0.0


def test_reset_clears_window():
    sampler = TemporalFrameSampler(window=2, interval_seconds=0.0)
    sampler.offer(_frame(1), 0.0)
    sampler.offer(_frame(2), 0.1)

    sampler.reset()

    assert len(sampler) == 0
    assert sampler.snapshot() == []


def test_zero_interval_accepts_every_frame():
    sampler = TemporalFrameSampler(window=3, interval_seconds=0.0)

    assert all(sampler.offer(_frame(i), 0.0) for i in range(3))
    assert len(sampler) == 3


def test_invalid_config_rejected():
    with pytest.raises(ValueError):
        TemporalFrameSampler(window=0)
    with pytest.raises(ValueError):
        TemporalFrameSampler(interval_seconds=-0.1)
