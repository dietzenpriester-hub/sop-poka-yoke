"""BOM 物料校验器"""

from loguru import logger


class BOMValidator:

    def __init__(self, vlm_client, yolo_detector) -> None:
        self.vlm = vlm_client
        self.detector = yolo_detector

    def validate(self, frame, bom_list: list[dict]) -> dict:
        detections = self.detector.detect(frame)
        detected_names = [d.class_name for d in detections]
        bom_desc = "\n".join(f"- {b['name']} (料号:{b['part_no']}, 数量:{b['qty']})" for b in bom_list)
        prompt_ctx = {
            "steps": [{"name": "物料校验", "description": f"核验以下物料:\n{bom_desc}"}],
            "current_step_index": 0,
        }
        vlm_result = self.vlm.classify_action([frame], prompt_ctx)
        result = {
            "result": "OK" if vlm_result.get("matches_expected") else "NG",
            "detected_objects": detected_names,
            "vlm_analysis": vlm_result,
            "bom_items": bom_list,
        }
        if result["result"] == "NG":
            logger.warning("物料校验异常: {}", vlm_result)
        return result
