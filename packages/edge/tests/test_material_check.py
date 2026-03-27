"""物料校验单元测试（Mock）"""

from unittest.mock import MagicMock

import numpy as np

from src.engine.material_check import BOMValidator
from src.inference.yolo_detector import Detection


def test_bom_validation_ok():
    mock_vlm = MagicMock()
    mock_vlm.classify_action.return_value = {"matches_expected": True, "confidence": 0.9}
    mock_detector = MagicMock()
    mock_detector.detect.return_value = [
        Detection(class_id=0, class_name="resistor", confidence=0.8, bbox=(0,0,10,10), center=(5,5))
    ]
    validator = BOMValidator(mock_vlm, mock_detector)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = validator.validate(frame, [{"part_no": "R100", "name": "电阻100Ω", "qty": 5}])
    assert result["result"] == "OK"
