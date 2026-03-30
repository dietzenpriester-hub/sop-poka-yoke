"""BOM 物料校验器"""

from loguru import logger


class BOMValidator:

    def __init__(self, vlm_client, yolo_detector) -> None:
        self.vlm = vlm_client
        self.detector = yolo_detector

    def validate(self, frame, bom_list: list[dict]) -> dict:
        detections = self.detector.detect(frame)
        detected_names = [d.class_name for d in detections]
        bom_desc = "\n".join(
            f"- {b.get('name', '')} (料号:{b.get('part_no', '')}, 数量:{b.get('qty', '')})"
            for b in bom_list
        )
        prompt_ctx = {
            "steps": [{"name": "物料校验", "description": f"核验以下物料:\n{bom_desc}"}],
            "current_step_index": 0,
        }
        vlm_result = self.vlm.classify_action([frame], prompt_ctx)
        vlm_ok = bool(vlm_result.get("matches_expected"))
        result = {
            "result": "OK" if vlm_ok else "NG",
            "detected_objects": detected_names,
            "vlm_analysis": vlm_result,
            "bom_items": bom_list,
            "low_confidence": False,
        }
        if not detections and vlm_ok:
            result["low_confidence"] = True
            logger.warning(
                "物料校验：YOLO 无检测但 VLM 判 OK，标记为低置信度（需人工复核）"
            )
        if result["result"] == "NG":
            logger.warning("物料校验异常: {}", vlm_result)
        return result
