"""测试配置"""

import pytest


@pytest.fixture
def sample_sop_template() -> dict:
    return {
        "name": "测试 SOP",
        "steps": [
            {"name": "拿起螺丝刀", "description": "从工具架上拿起螺丝刀"},
            {"name": "拧螺丝", "description": "将螺丝拧入 PCB 板"},
            {"name": "放下螺丝刀", "description": "将螺丝刀放回工具架"},
        ],
    }
