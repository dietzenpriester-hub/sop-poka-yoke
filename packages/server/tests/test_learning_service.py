"""标准学习服务质量门槛测试。"""

import re

import pytest

from src.api.learning import LEARNING_NAME_PATTERN
from src.models.learning_task import LearningTask
from src.services.ai.frame_extractor import ActionSegment, FrameExtractor
from src.services.learning_service import LearningService


_svc = LearningService()


def test_learning_name_pattern_allows_internal_space():
    assert re.fullmatch(LEARNING_NAME_PATTERN, "测试 1")
    assert re.fullmatch(LEARNING_NAME_PATTERN, "PCB-A100 Rev1")
    assert not re.fullmatch(LEARNING_NAME_PATTERN, "测试  1")
    assert not re.fullmatch(LEARNING_NAME_PATTERN, "测试/1")


def _valid_step(name: str = "放置物料") -> dict:
    return {
        "index": 0,
        "name": name,
        "description": "将物料放入治具",
        "ok_criteria": "物料完全进入治具并贴合定位边",
        "ng_criteria": "物料未放入、偏位或未贴合定位边",
        "required_objects": ["material"],
        "timeout_seconds": 30,
    }


def test_quality_gate_flags_low_confidence_and_coarse_steps():
    report = _svc._evaluate_quality(
        [_valid_step()],
        {"duration_sec": 19.3, "segments_count": 1, "confidence": 0.5},
    )

    codes = {issue["code"] for issue in report["issues"]}
    assert report["passed"] is False
    assert report["status"] == "needs_review"
    assert {"low_confidence", "few_steps_for_duration", "coarse_segmentation"} <= codes


def test_quality_gate_allows_manual_review_for_reviewable_issues():
    report = _svc._evaluate_quality(
        [_valid_step()],
        {"duration_sec": 19.3, "segments_count": 1, "confidence": 0.5},
        manual_reviewed=True,
    )

    assert report["passed"] is True
    assert report["manual_reviewed"] is True


@pytest.mark.asyncio
async def test_update_steps_moves_reviewed_task_to_completed(db_session):
    task = LearningTask(
        task_id="learn-review-1",
        product_model="PCB-A100",
        process_name="装配",
        video_path="sop-learning/test.mp4",
        status="needs_review",
        progress=1.0,
        steps=[],
        analysis_detail={"duration_sec": 19.3, "segments_count": 1, "confidence": 0.5},
    )
    db_session.add(task)
    await db_session.commit()

    updated = await _svc.update_steps("learn-review-1", [_valid_step()], db_session)

    assert updated.status == "completed"
    assert updated.analysis_detail["quality"]["manual_reviewed"] is True

    result = await _svc.confirm_and_generate("learn-review-1", db_session)
    assert result["template_id"] is not None
    assert result["step_count"] == 1


@pytest.mark.asyncio
async def test_confirm_rejects_unreviewed_low_quality_task(db_session):
    task = LearningTask(
        task_id="learn-review-2",
        product_model="PCB-A100",
        process_name="装配",
        video_path="sop-learning/test.mp4",
        status="needs_review",
        progress=1.0,
        steps=[_valid_step()],
        analysis_detail={
            "quality": {
                "passed": False,
                "status": "needs_review",
                "issues": [{"code": "low_confidence", "message": "低置信度", "severity": "warning"}],
            },
        },
    )
    db_session.add(task)
    await db_session.commit()

    with pytest.raises(ValueError, match="需要人工复核"):
        await _svc.confirm_and_generate("learn-review-2", db_session)


@pytest.mark.asyncio
async def test_retry_analysis_resets_failed_task(db_session, monkeypatch):
    task = LearningTask(
        task_id="learn-retry-1",
        product_model="PCB-A100",
        process_name="装配",
        video_path="sop-learning/test.mp4",
        status="failed",
        progress=0.4,
        steps=[_valid_step()],
        error_message="模型不可用",
        analysis_detail={"phase": "失败"},
    )
    db_session.add(task)
    await db_session.commit()

    scheduled = []
    monkeypatch.setattr("src.services.learning_service.asyncio.create_task", scheduled.append)

    updated = await _svc.retry_analysis("learn-retry-1", db_session)

    assert updated.status == "queued"
    assert updated.progress == 0.0
    assert updated.steps == []
    assert updated.error_message == ""
    assert updated.completed_at is None
    assert updated.analysis_detail["phase"] == "重新排队"
    assert len(scheduled) == 1
    scheduled[0].close()


def test_frame_extractor_uses_uniform_fallback_for_coarse_long_video():
    extractor = FrameExtractor(coarse_fallback_min_duration_sec=8.0)
    segment = ActionSegment(segment_id=0, start_sec=0.0, end_sec=12.0)

    assert extractor._should_use_uniform_fallback([segment], duration_sec=12.0, sampled_count=20)
    assert not extractor._should_use_uniform_fallback([segment], duration_sec=5.0, sampled_count=20)
