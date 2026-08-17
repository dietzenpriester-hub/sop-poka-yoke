"""边缘端 VLM prompt 与图像编码测试。"""

import base64

import cv2
import numpy as np
import pytest

from src.engine.state_machine import SOPStateMachine
from src.inference.vlm_recognizer import VLMClient


@pytest.fixture
def client():
    c = VLMClient()
    yield c
    c.close()


def _frame(value: int, size: int = 64) -> np.ndarray:
    return np.full((size, size, 3), value, dtype=np.uint8)


def _jpeg_b64(frame: np.ndarray) -> str:
    _, buf = cv2.imencode(".jpg", frame)
    return base64.b64encode(buf).decode("ascii")


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
        prompt = client._build_prompt(
            {
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
            }
        )
    finally:
        client.close()

    assert "必选对象：material、fixture" in prompt
    assert "OK 判定：物料完全进入治具并贴合定位边" in prompt
    assert "NG 判定：物料偏位或未贴合定位边" in prompt


def test_montage_lays_frames_out_in_grid():
    frames = [_frame(v) for v in (10, 20, 30, 40)]

    montage = VLMClient._build_montage(frames)

    assert montage.shape == (128, 128, 3)


def test_montage_pads_incomplete_grid():
    montage = VLMClient._build_montage([_frame(10), _frame(20), _frame(30)])

    assert montage.shape == (128, 128, 3)


def test_montage_normalizes_mismatched_frame_sizes():
    montage = VLMClient._build_montage([_frame(10, size=64), _frame(20, size=48)])

    assert montage.shape == (48, 96, 3)


def test_single_frame_skips_montage(client):
    _, count = client._encode_sequence([_frame(10)])

    assert count == 1


def test_multi_frame_sequence_reports_frame_count(client):
    encoded, count = client._encode_sequence([_frame(10), _frame(20), _frame(30)])

    assert count == 3
    assert encoded


def test_sequence_ignores_empty_frames(client):
    _, count = client._encode_sequence([_frame(10), np.empty((0, 0, 3), dtype=np.uint8)])

    assert count == 1


def test_prompt_describes_reference_and_sequence_order(client):
    prompt = client._build_prompt(
        {"current_step_index": 0, "steps": [{"name": "拧螺丝"}]},
        frame_count=4,
        has_reference=True,
    )

    assert "图1：该步骤的标准参考画面" in prompt
    assert "图2：当前工位的连续画面" in prompt
    assert "1 最早，4 最新" in prompt
    assert "标准参考画面对比" in prompt


def test_multi_frame_prompt_anchors_judgement_on_latest_cell(client):
    """多帧判定必须锚定最新一格。

    早期版本让模型「找帧间变化」，结果它把手中物件的高度变化读成了
    「已放回桌面」，对从未发生的步骤谎报完成——防呆场景下会直接导致误放行。
    """
    prompt = client._build_prompt(
        {"current_step_index": 0, "steps": [{"name": "拧螺丝"}]},
        frame_count=4,
        has_reference=False,
    )

    assert "判定以第4格（最新一格）的画面为准" in prompt
    assert "不能据此推断它已被放下、装上或取走" in prompt
    assert "画面静止不代表没有执行" in prompt


def test_place_prompt_requires_visible_release(client):
    """place 类必须看见脱手，不能把持握中的位移读成放下。"""
    prompt = client._build_prompt(
        {
            "current_step_index": 0,
            "steps": [{"name": "将手机放回桌面", "action_type": "place"}],
        },
        frame_count=1,
        has_reference=False,
    )

    assert "放置/脱手" in prompt
    assert "只要物件仍被握住，必须判 false" in prompt
    assert "不要因为当前期望是「放下」就把位移解释为放下" in prompt
    assert "物件仍在手里时必须 false" in prompt


def test_place_prompt_overrides_multi_frame_motion_language(client):
    prompt = client._build_prompt(
        {
            "current_step_index": 0,
            "steps": [{"name": "将手机放回桌面", "action_type": "place"}],
        },
        frame_count=4,
        has_reference=False,
    )

    assert "放置/脱手" in prompt
    assert "判定以第4格（最新一格）的画面为准" not in prompt


def test_prompt_omits_sequence_note_for_single_frame(client):
    prompt = client._build_prompt(
        {"current_step_index": 0, "steps": [{"name": "拧螺丝"}]},
        frame_count=1,
        has_reference=False,
    )

    assert "图1：当前工位画面" in prompt
    assert "时间顺序" not in prompt


def test_reference_image_decoded_and_cached(client):
    ref = _jpeg_b64(_frame(120))
    ctx = {"current_step_index": 0, "steps": [{"name": "拧螺丝", "reference_frame_b64": ref}]}

    first = client._reference_image(ctx)
    second = client._reference_image(ctx)

    assert first
    assert first == second
    assert client._reference_cache


def test_reference_image_accepts_data_url_prefix(client):
    ref = _jpeg_b64(_frame(120))
    ctx = {
        "current_step_index": 0,
        "steps": [{"name": "拧螺丝", "reference_frame_b64": f"data:image/jpeg;base64,{ref}"}],
    }

    assert client._reference_image(ctx)


def test_invalid_reference_image_degrades_silently(client):
    ctx = {"current_step_index": 0, "steps": [{"name": "拧螺丝", "reference_frame_b64": "not-base64!!"}]}

    assert client._reference_image(ctx) == ""


def test_reference_image_skipped_when_disabled():
    client = VLMClient(use_reference_frame=False)
    try:
        ctx = {
            "current_step_index": 0,
            "steps": [{"name": "拧螺丝", "reference_frame_b64": _jpeg_b64(_frame(120))}],
        }
        assert client._reference_image(ctx) == ""
    finally:
        client.close()


def test_reference_image_skipped_in_global_detect(client):
    ctx = {
        "global_detect": True,
        "current_step_index": 0,
        "steps": [{"name": "拧螺丝", "reference_frame_b64": _jpeg_b64(_frame(120))}],
    }

    assert client._reference_image(ctx) == ""


def test_global_prompt_explains_frame_order(client):
    prompt = client._build_prompt(
        {"global_detect": True, "steps": [{"name": "拧螺丝"}], "completed_indices": []},
        frame_count=4,
    )

    assert "1 最早，4 最新" in prompt
    assert "matched_step" in prompt


def test_prompt_separates_idle_from_wrong_action(client):
    prompt = client._build_prompt(
        {"current_step_index": 0, "steps": [{"name": "拧螺丝"}]},
        frame_count=1,
        has_reference=False,
    )

    assert '"idle": true或false' in prompt
    assert '"ng_violation": true或false' in prompt
    assert "禁止为了迎合期望步骤" in prompt
    assert "等待不是错误" in prompt
    assert "尚未开始、仍在等待" in prompt
    assert "不要因为动作还没发生、或发生得比预想慢，就判成错误" in prompt


def test_pick_prompt_treats_held_off_origin_as_done(client):
    prompt = client._build_prompt(
        {
            "current_step_index": 0,
            "steps": [{"name": "从桌面取起手机", "action_type": "pick"}],
        },
        frame_count=1,
        has_reference=False,
    )

    assert "取拿」结果态" in prompt
    assert "即使动作已经停住，也必须判 true" in prompt
    assert "不要因为握稳就改成 idle" in prompt
    assert "正在离开原位" not in prompt


def test_screw_prompt_requires_seated_result(client):
    prompt = client._build_prompt(
        {
            "current_step_index": 0,
            "steps": [{"name": "拧紧螺丝", "action_type": "screw"}],
        },
        frame_count=1,
        has_reference=False,
    )

    assert "拧紧/组装」结果态" in prompt
    assert "不要因为电批在转" in prompt
    assert "悬停、对准、旋转中都还不算" in prompt
    assert "已经就位后即使动作停住，仍应判 true" in prompt


def test_validate_match_clears_idle():
    result = VLMClient._validate_action_result(
        {"action": "正在拧螺丝", "matches_expected": True, "idle": True, "confidence": 0.9}
    )

    assert result["matches_expected"] is True
    assert result["idle"] is False


def test_validate_missing_idle_on_mismatch_is_waiting():
    result = VLMClient._validate_action_result({"action": "双手搭在桌面", "matches_expected": False, "confidence": 0.8})

    assert result["matches_expected"] is False
    assert result["idle"] is True


def test_validate_ng_violation_requires_explicit_flag():
    waiting = VLMClient._validate_action_result(
        {"action": "仍握着手机", "matches_expected": False, "idle": False, "confidence": 0.9}
    )
    defect = VLMClient._validate_action_result(
        {
            "action": "手机掉到地上",
            "matches_expected": False,
            "idle": False,
            "ng_violation": True,
            "confidence": 0.9,
        }
    )

    assert waiting["ng_violation"] is False
    assert defect["ng_violation"] is True


def test_empty_frames_returns_unknown(client):
    result = client.classify_action([], {"steps": [{"name": "拧螺丝"}], "current_step_index": 0})

    assert result["action"] == "unknown"
    assert result["confidence"] == 0.0
