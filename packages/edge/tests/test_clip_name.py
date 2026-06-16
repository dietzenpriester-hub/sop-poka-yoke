"""录像文件名解析测试：用于上传 MinIO 后回填 step/video。"""

import pytest

from src.main import _parse_clip_name


def test_parse_standard_clip_name():
    sn, step, event = _parse_clip_name(
        "/data/clips/SN-001_step2_STEP_NG_20250101_120000.mp4"
    )
    assert sn == "SN-001"
    assert step == 2
    assert event == "STEP_NG"


def test_parse_auto_sn_with_hyphens():
    sn, step, event = _parse_clip_name(
        "AUTO-20250101-120000_step0_STEP_NG_20250101_120005.mp4"
    )
    assert sn == "AUTO-20250101-120000"
    assert step == 0
    assert event == "STEP_NG"


@pytest.mark.parametrize(
    "bad",
    [
        "not_a_clip.mp4",
        "SN-001_step2_STEP_NG.mp4",
        "SN-001_stepX_STEP_NG_20250101_120000.mp4",
        "SN-001_step2_STEP_NG_20250101_120000.txt",
    ],
)
def test_parse_invalid_returns_none(bad):
    assert _parse_clip_name(bad) is None
