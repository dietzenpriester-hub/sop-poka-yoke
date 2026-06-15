"""SOP 状态机单元测试"""

from unittest.mock import patch

import pytest

from src.engine.state_machine import SOPStateMachine, SOPStatus


@pytest.fixture
def sop_machine():
    template = {
        "name": "测试 SOP",
        "steps": [
            {"name": "拿起螺丝刀", "description": "从工具架上拿起螺丝刀"},
            {"name": "拧螺丝", "description": "将螺丝拧入 PCB 板"},
            {"name": "放下螺丝刀", "description": "将螺丝刀放回工具架"},
        ],
    }
    machine = SOPStateMachine(template, debounce_seconds=0)
    machine.start("TEST_SN_001")
    return machine


def _advance_step_ok(machine: SOPStateMachine) -> None:
    """连续达到 min_consecutive_pass 次匹配后确认一步。"""
    for _ in range(machine.min_consecutive_pass):
        machine.process_action({"matches_expected": True, "confidence": 0.9})


def _advance_step_ng(machine: SOPStateMachine) -> dict:
    """连续达到 ng_tolerance 次不匹配后进入 STEP_NG。"""
    result = {}
    for _ in range(machine.ng_tolerance):
        result = machine.process_action({"matches_expected": False, "confidence": 0.3})
    return result


def test_normal_flow(sop_machine):
    # 默认策略：每步需要连续多次匹配，降低 VLM 单帧误判风险。
    for _ in range(3):
        _advance_step_ok(sop_machine)
    assert sop_machine.status == SOPStatus.COMPLETE


def test_wrong_action(sop_machine):
    result = _advance_step_ng(sop_machine)
    assert result["event"] == "step_ng"
    assert sop_machine.status == SOPStatus.STEP_NG


def test_step_ng_blocks_until_reset_or_override(sop_machine):
    _advance_step_ng(sop_machine)
    blocked = sop_machine.process_action({"matches_expected": True, "confidence": 0.9})
    assert blocked["type"] == "blocked"
    assert "STEP_NG" in blocked["reason"]


def test_override(sop_machine):
    result = sop_machine.override("BADGE_001", "AI 误判")
    assert result["event"] == "override_ok"
    assert sop_machine.current_step_index == 1


def test_timeout_detection(sample_sop_template):
    """超时检测：当前步停留超过 timeout_seconds 后进入 TIMEOUT。"""
    template = {
        **sample_sop_template,
        "steps": [
            {**sample_sop_template["steps"][0], "timeout_seconds": 10.0},
            *sample_sop_template["steps"][1:],
        ],
    }
    machine = SOPStateMachine(template, debounce_seconds=0)
    t0 = 1_000_000.0
    with patch("src.engine.state_machine.time") as mock_time:
        mock_time.time.return_value = t0
        machine.start("SN_TIMEOUT")
        mock_time.time.return_value = t0 + 100.0
        out = machine.check_timeout()
        assert out is not None
        assert out["event"] == "timeout"
        assert machine.status == SOPStatus.TIMEOUT


def test_reset_after_ng(sample_sop_template):
    """NG 后 reset 恢复为 IDLE，可重新 start。"""
    machine = SOPStateMachine(sample_sop_template, debounce_seconds=0)
    machine.start("SN_NG")
    _advance_step_ng(machine)
    assert machine.status == SOPStatus.STEP_NG
    machine.reset()
    assert machine.status == SOPStatus.IDLE
    assert machine.work_order_sn is None
    machine.start("SN_NEW")
    assert machine.status == SOPStatus.RUNNING
    _advance_step_ok(machine)
    assert machine.current_step_index == 1


def test_reset_after_timeout(sample_sop_template):
    """超时后 reset 清除 TIMEOUT，回到 IDLE。"""
    template = {
        **sample_sop_template,
        "steps": [
            {**sample_sop_template["steps"][0], "timeout_seconds": 5.0},
            *sample_sop_template["steps"][1:],
        ],
    }
    machine = SOPStateMachine(template, debounce_seconds=0)
    t0 = 500.0
    with patch("src.engine.state_machine.time") as mock_time:
        mock_time.time.return_value = t0
        machine.start("SN_TO")
        mock_time.time.return_value = t0 + 10.0
        machine.check_timeout()
    assert machine.status == SOPStatus.TIMEOUT
    machine.reset()
    assert machine.status == SOPStatus.IDLE


def test_complete_flow_with_override(sample_sop_template):
    """含 override 的完整流程：首步 OK → 第二步 NG → override → 末步 OK 完成。"""
    machine = SOPStateMachine(sample_sop_template, debounce_seconds=0)
    machine.start("SN_FULL")
    _advance_step_ok(machine)
    assert machine.current_step_index == 1
    assert machine.status == SOPStatus.STEP_OK
    _advance_step_ng(machine)
    assert machine.status == SOPStatus.STEP_NG
    r = machine.override("B001", "跳过误判步骤")
    assert r["event"] == "override_ok"
    assert machine.status == SOPStatus.RUNNING
    _advance_step_ok(machine)
    assert machine.status == SOPStatus.COMPLETE


def test_consecutive_pass_requires_stable_matches(sample_sop_template):
    """连续通过计数：中途不匹配会清零，需重新累计稳定匹配。"""
    machine = SOPStateMachine(sample_sop_template, debounce_seconds=1.0)
    machine.start("SN_STABLE")
    r1 = machine.process_action({"matches_expected": True, "confidence": 0.9})
    assert r1["event"] == "matching"

    r2 = machine.process_action({"matches_expected": False, "confidence": 0.3})
    assert r2["event"] == "ng_pending"

    for _ in range(machine.min_consecutive_pass - 1):
        r = machine.process_action({"matches_expected": True, "confidence": 0.9})
        assert r["event"] == "matching"
    r3 = machine.process_action({"matches_expected": True, "confidence": 0.9})
    assert r3["event"] == "step_ok"


def test_idle_status_initial(sample_sop_template):
    """初始状态为 IDLE。"""
    machine = SOPStateMachine(sample_sop_template, debounce_seconds=0)
    assert machine.status == SOPStatus.IDLE


def test_start_sets_running(sample_sop_template):
    """start 后进入 RUNNING。"""
    machine = SOPStateMachine(sample_sop_template, debounce_seconds=0)
    machine.start("SN_RUN")
    assert machine.status == SOPStatus.RUNNING
    assert machine.work_order_sn == "SN_RUN"
