"""MQTTTopics 单元测试：主题格式与 station_id 校验。"""

import sys
from pathlib import Path

import pytest

# 将 packages 加入路径，便于 `from shared.xxx` 导入
_PACKAGES = Path(__file__).resolve().parents[2]
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from shared.mqtt_topics import MQTTTopics  # noqa: E402


def test_detection_topic_format():
    """检测主题应为 `{prefix}/{station_id}/detection`。"""
    topics = MQTTTopics()
    assert topics.detection("line01") == "sop/line01/detection"


def test_step_complete_topic_format():
    """步骤完成主题应为 `{prefix}/{station_id}/step/complete`。"""
    topics = MQTTTopics()
    assert topics.step_complete("S-A_1") == "sop/S-A_1/step/complete"


def test_alert_topic_format():
    """告警主题为 `{prefix}/{station_id}/alert/raise`。"""
    topics = MQTTTopics()
    assert topics.alert_raise("st1") == "sop/st1/alert/raise"


@pytest.mark.parametrize(
    "invalid_id",
    [
        "",
        "a b",
        "a/b",
        "a.b",
        "@",
        "工位",
        "a\nb",
    ],
)
def test_invalid_station_id_rejected(invalid_id):
    """非法 station_id（空串、空白、路径符、非 ASCII 等）应抛出 ValueError。"""
    topics = MQTTTopics()
    with pytest.raises(ValueError, match="非法字符"):
        topics.detection(invalid_id)


def test_custom_prefix():
    """自定义前缀应出现在所有生成主题中。"""
    topics = MQTTTopics("prod")
    sid = "w1"
    assert topics.detection(sid) == f"prod/{sid}/detection"
    assert topics.step_complete(sid) == f"prod/{sid}/step/complete"
    assert topics.alert_raise(sid) == f"prod/{sid}/alert/raise"


def test_default_prefix():
    """未指定或空前缀时默认使用 `sop`。"""
    assert MQTTTopics.DEFAULT_PREFIX == "sop"
    t1 = MQTTTopics()
    assert t1.detection("x") == "sop/x/detection"
    # 仅空白或空字符串时回退为默认前缀
    t2 = MQTTTopics("   ")
    assert t2.detection("x") == "sop/x/detection"
    t3 = MQTTTopics("")
    assert t3.detection("x") == "sop/x/detection"
