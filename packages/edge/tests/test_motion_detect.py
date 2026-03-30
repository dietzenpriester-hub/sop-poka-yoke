"""运动检测 / 关键帧提取单元测试"""

import numpy as np

from src.capture.motion_detect import KeyframeExtractor


def test_static_scene_no_keyframe():
    """静态场景：连续相同帧在背景稳定后不再判为关键帧（首帧实现上恒为关键帧）。"""
    ext = KeyframeExtractor(diff_threshold=30.0, min_area_ratio=0.02)
    frame = np.full((120, 160, 3), 128, dtype=np.uint8)
    # 首帧无上一帧对比，实现上视为运动
    assert ext.is_keyframe(frame)
    # 多帧相同输入，帧差与前景占比均趋近 0
    last = True
    for _ in range(120):
        last = ext.is_keyframe(frame)
    assert not last


def test_motion_triggers_keyframe():
    """相邻帧差异明显时产生关键帧。"""
    ext = KeyframeExtractor(diff_threshold=20.0, min_area_ratio=0.001)
    a = np.zeros((100, 100, 3), dtype=np.uint8)
    b = np.full((100, 100, 3), 255, dtype=np.uint8)
    assert ext.is_keyframe(a)
    assert ext.is_keyframe(b)


def test_reset_clears_state():
    """reset 后内部状态清空，再次处理首帧行为与新建实例一致。"""
    ext = KeyframeExtractor(diff_threshold=30.0, min_area_ratio=0.02)
    f = np.full((64, 64, 3), 64, dtype=np.uint8)
    ext.is_keyframe(f)
    ext.is_keyframe(f)
    ext.reset()
    assert ext._prev_gray is None
    assert ext.is_keyframe(f)
