"""按步骤类型决定送给 VLM 的帧策略。

评测表明：4 帧网格能提高 inspect 等持续状态的召回率，但 pick / place 这类
「结果态」步骤会被网格里的旧画面干扰——桌上与手里混在同一格，会把连续通过
打断（滞后），或把位移读成已经放下（误放行）。这两类只看当前帧。

乱序检测（global_detect）没有「当前步骤」，不适用本分流，仍走完整时序窗口。
"""

from __future__ import annotations

import os
from typing import Any

# 终点状态判定：必须看见物件已脱手 / 已就位，时序位移会被误读成完成
RELEASE_ACTION_TYPES = frozenset(
    {
        "place",
        "put",
        "put_down",
        "drop",
        "release",
        "unload",
    }
)

# 取拿结果态：物件已在手里并离开原位即为完成；时序网格会混入「仍在桌上」的旧帧
TRANSITION_ACTION_TYPES = frozenset(
    {
        "pick",
        "pickup",
        "pick_up",
        "take",
        "grab",
        "pick_place",
    }
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def adaptive_window_enabled() -> bool:
    """默认开启。设 SOP_VLM_ADAPTIVE_WINDOW=0 可强制所有步骤走完整时序窗口。"""
    return _env_bool("SOP_VLM_ADAPTIVE_WINDOW", True)


def normalize_action_type(action_type: str | None) -> str:
    return (action_type or "").strip().lower()


def is_release_step(action_type: str | None) -> bool:
    """是否属于「放置 / 脱手」类步骤。"""
    return normalize_action_type(action_type) in RELEASE_ACTION_TYPES


def is_transition_step(action_type: str | None) -> bool:
    """是否属于「取拿」类步骤。看结果态：已握住并离开原位即算完成。"""
    return normalize_action_type(action_type) in TRANSITION_ACTION_TYPES


def uses_snapshot_frame(action_type: str | None) -> bool:
    """取拿 / 放置都按当前画面的结果态判定，不看运动轨迹。"""
    return is_release_step(action_type) or is_transition_step(action_type)


def uses_temporal_window(action_type: str | None, *, adaptive: bool | None = None) -> bool:
    """取拿、放置在自适应开启时只用当前帧；inspect 等持续状态仍走时序窗口。"""
    enabled = adaptive_window_enabled() if adaptive is None else adaptive
    if not enabled:
        return True
    return not uses_snapshot_frame(action_type)


def select_frames_for_step(
    action_type: str | None,
    sequence: list[Any],
    current_frame: Any,
    *,
    adaptive: bool | None = None,
) -> list[Any]:
    """选出本次应提交给 VLM 的帧。

    取拿 / 放置必须用当前帧而不是窗口末帧：采样器会丢掉间隔内的帧，
    窗口末帧可能已过时，不能代表「此刻是否已离开原位 / 已脱手」。
    """
    if uses_temporal_window(action_type, adaptive=adaptive):
        return sequence or [current_frame]
    return [current_frame]
