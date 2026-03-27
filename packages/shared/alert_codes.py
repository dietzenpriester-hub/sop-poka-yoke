"""报警代码定义"""


class AlertCode:
    STEP_SEQUENCE_ERROR = "E001"
    STEP_TIMEOUT = "E002"
    MATERIAL_MISMATCH = "E003"
    COMPLETION_FAIL = "E004"
    STEP_SKIP = "W001"
    LOW_CONFIDENCE = "W002"
    OVERRIDE_APPLIED = "I001"
    WORKORDER_COMPLETE = "I002"
    SYSTEM_OFFLINE = "C001"
    GPU_OVERHEAT = "C002"


ALERT_DESCRIPTIONS = {
    AlertCode.STEP_SEQUENCE_ERROR: "步骤顺序错误",
    AlertCode.STEP_TIMEOUT: "步骤超时未完成",
    AlertCode.MATERIAL_MISMATCH: "物料不匹配",
    AlertCode.COMPLETION_FAIL: "完工检验不通过",
    AlertCode.STEP_SKIP: "步骤跳步警告",
    AlertCode.LOW_CONFIDENCE: "识别置信度过低",
    AlertCode.OVERRIDE_APPLIED: "人工强制放行",
    AlertCode.WORKORDER_COMPLETE: "工单完成",
    AlertCode.SYSTEM_OFFLINE: "系统离线",
    AlertCode.GPU_OVERHEAT: "GPU 温度过高",
}
