"""边缘端 VLM prompt 测试。"""

from src.engine.state_machine import SOPStateMachine
from src.inference.vlm_recognizer import VLMClient


def test_state_machine_keeps_learning_criteria_fields():
    template = {
        "name": "学习模板",
        "steps": [
            {
                "name": "放置物料",
                "description": "将物料放入治具",
                "ok_criteria": "物料完全进入治具并贴合定位边",
                "ng_criteria": "物料偏位或未贴合定位边",
                "reference_frame_b64": "abc",
                "reference_frame_timestamp": 1.2,
            }
        ],
    }

    machine = SOPStateMachine(template)

    assert machine.steps[0].ok_criteria == "物料完全进入治具并贴合定位边"
    assert machine.steps[0].ng_criteria == "物料偏位或未贴合定位边"
    assert machine.steps[0].reference_frame_b64 == "abc"
    assert machine.steps[0].reference_frame_timestamp == 1.2


def test_vlm_prompt_includes_ok_ng_criteria_and_required_objects():
    client = VLMClient()
    try:
        prompt = client._build_prompt({
            "current_step_index": 0,
            "steps": [
                {
                    "name": "放置物料",
                    "description": "将物料放入治具",
                    "required_objects": ["material", "fixture"],
                    "ok_criteria": "物料完全进入治具并贴合定位边",
                    "ng_criteria": "物料偏位或未贴合定位边",
                }
            ],
        })
    finally:
        client.close()

    assert "必选对象：material、fixture" in prompt
    assert "OK 判定：物料完全进入治具并贴合定位边" in prompt
    assert "NG 判定：物料偏位或未贴合定位边" in prompt
