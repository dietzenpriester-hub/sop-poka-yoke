"""完工视觉比对检测器"""

import cv2
from loguru import logger


class VisualInspector:
    MAX_WIDTH = 640
    MAX_HEIGHT = 480
    SIMILARITY_THRESHOLD = 0.7

    def __init__(self, vlm_client, yolo_detector) -> None:
        self.vlm = vlm_client
        self.detector = yolo_detector

    def inspect(self, frame, reference_image_path: str, check_items: list[str]) -> dict:
        from pathlib import Path
        rp = Path(reference_image_path).resolve()
        allowed_root = Path(__file__).resolve().parents[3] / "data"
        try:
            rp.relative_to(allowed_root)
        except ValueError:
            return {"result": "ERROR", "message": f"参考图路径不在允许目录内: {rp}"}
        ref_image = cv2.imread(str(rp))
        if ref_image is None:
            return {"result": "ERROR", "message": "参考图加载失败"}
        detections = self.detector.detect(frame)
        items_desc = "\n".join(f"- {item}" for item in check_items)
        prompt_ctx = {
            "steps": [{"name": "完工检验", "description": f"对比参考图与实际完工图，检查:\n{items_desc}"}],
            "current_step_index": 0,
        }
        vlm_result = self.vlm.classify_action([frame, ref_image], prompt_ctx)
        resize_wh = (self.MAX_WIDTH, self.MAX_HEIGHT)
        gray_frame = cv2.cvtColor(cv2.resize(frame, resize_wh), cv2.COLOR_BGR2GRAY)
        gray_ref = cv2.cvtColor(cv2.resize(ref_image, resize_wh), cv2.COLOR_BGR2GRAY)
        if gray_frame.shape != gray_ref.shape:
            logger.error("完工比对尺寸不一致: frame={} ref={}", gray_frame.shape, gray_ref.shape)
            return {"result": "ERROR", "message": "参考图与当前帧尺寸不一致"}
        similarity = float(cv2.matchTemplate(gray_frame, gray_ref, cv2.TM_CCOEFF_NORMED).max())
        passed = vlm_result.get("matches_expected", False) and similarity > self.SIMILARITY_THRESHOLD
        return {
            "result": "PASS" if passed else "FAIL",
            "similarity_score": similarity,
            "vlm_analysis": vlm_result,
            "detected_features": [d.class_name for d in detections],
            "check_items": check_items,
        }
