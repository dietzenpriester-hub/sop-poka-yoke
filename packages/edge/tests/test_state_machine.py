"""SOP 状态机单元测试"""

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


def test_normal_flow(sop_machine):
    # debounce_seconds=0 时仍需两次匹配：首次进入防抖，第二次在同一时间窗口内确认步骤
    for _ in range(3):
        sop_machine.process_action({"matches_expected": True, "confidence": 0.9})
        sop_machine.process_action({"matches_expected": True, "confidence": 0.9})
    assert sop_machine.status == SOPStatus.COMPLETE


def test_wrong_action(sop_machine):
    result = sop_machine.process_action({"matches_expected": False, "confidence": 0.3})
    assert result["event"] == "step_ng"
    assert sop_machine.status == SOPStatus.STEP_NG


def test_step_ng_blocks_until_reset_or_override(sop_machine):
    sop_machine.process_action({"matches_expected": False, "confidence": 0.3})
    blocked = sop_machine.process_action({"matches_expected": True, "confidence": 0.9})
    assert blocked["type"] == "blocked"
    assert "STEP_NG" in blocked["reason"]


def test_override(sop_machine):
    result = sop_machine.override("BADGE_001", "AI 误判")
    assert result["event"] == "override_ok"
    assert sop_machine.current_step_index == 1
