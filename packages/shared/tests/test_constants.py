"""constants 与告警代码相关常量测试。"""

import re
import sys
from pathlib import Path

# 将 packages 加入路径，便于 `from shared.xxx` 导入
_PACKAGES = Path(__file__).resolve().parents[2]
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from shared.alert_codes import AlertCode  # noqa: E402
from shared.constants import APP_VERSION  # noqa: E402

# 语义化版本：主.次.修订（与项目约定一致）
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

# 告警代码首字母与 default_severity 的对应关系（与 alert_codes.AlertCode 一致）
_SEVERITY_BY_PREFIX = {"E": "ERROR", "W": "WARN", "I": "INFO", "C": "CRITICAL"}


def test_app_version_format():
    """APP_VERSION 应为 `x.y.z` 形式的版本号。"""
    assert _VERSION_PATTERN.match(APP_VERSION), f"非法版本格式: {APP_VERSION!r}"


def test_alert_codes_exist():
    """每个 AlertCode 枚举成员应有非空值与描述。"""
    for code in AlertCode:
        assert code.value, f"{code.name} 应有 value"
        assert code.description, f"{code.name} 应有 description"


def test_alert_code_severity():
    """每个告警代码应有与首字母一致的严重度，且不为 UNKNOWN。"""
    for code in AlertCode:
        prefix = code.value[0]
        expected = _SEVERITY_BY_PREFIX.get(prefix)
        assert expected is not None, f"{code.value} 首字符无映射: {prefix!r}"
        assert code.default_severity == expected
        assert code.default_severity != "UNKNOWN"
