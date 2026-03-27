"""多模态大模型推理客户端（通过 Ollama API）"""

import base64
import json
import re

import cv2
import httpx
import numpy as np
from loguru import logger


class VLMClient:

    def __init__(
        self, base_url: str = "http://localhost:11434", model: str = "qwen2-vl:2b", timeout: float = 10.0
    ) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def classify_action(self, frames: list[np.ndarray], sop_context: dict) -> dict:
        images_b64 = [self._frame_to_base64(f) for f in frames]
        prompt = self._build_prompt(sop_context)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt, "images": images_b64}],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 200},
        }
        try:
            resp = self.client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            result = resp.json()
            return self._parse_response(result["message"]["content"])
        except Exception as e:
            logger.error("VLM 推理失败: {}", e)
            return {"action": "unknown", "confidence": 0.0, "description": str(e)}

    def classify_action_with_retry(self, frames: list, sop_context: dict, max_retries: int = 2) -> dict:
        for attempt in range(max_retries + 1):
            result = self.classify_action(frames, sop_context)
            if not result.get("needs_human_review"):
                return result
            if attempt < max_retries:
                logger.info("VLM 解析失败，重试 {}/{}", attempt + 1, max_retries)
        return result

    def _frame_to_base64(self, frame: np.ndarray) -> str:
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buffer).decode("utf-8")

    def _build_prompt(self, ctx: dict) -> str:
        steps_desc = "\n".join(
            f"  步骤{i + 1}: {s['name']} — {s.get('description', '')}"
            for i, s in enumerate(ctx.get("steps", []))
        )
        current = ctx.get("current_step_index", 0)
        expected = ctx.get("steps", [{}])[current].get("name", "未知") if ctx.get("steps") else "未知"
        return f"""你是一个工业 SOP 动作识别专家。

当前工序的 SOP 步骤：
{steps_desc}

当前期望步骤（第 {current + 1} 步）：{expected}

请分析图片中操作员正在执行的动作，返回 JSON 格式：
{{"action": "具体动作描述", "matches_expected": true/false, "confidence": 0.0-1.0, "details": "补充说明"}}

仅返回 JSON，不要其他内容。"""

    def _parse_response(self, content: str) -> dict:
        content = content.strip()
        candidates = [content]
        json_blocks = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", content, re.DOTALL)
        candidates.extend(json_blocks)
        if content.startswith("```"):
            inner = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            candidates.insert(0, inner)
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict) and "action" in parsed:
                    return self._validate_action_result(parsed)
            except (json.JSONDecodeError, ValueError):
                continue
        logger.warning("VLM 响应解析失败，触发人工介入标记: {}", content[:200])
        return {
            "action": "parse_failed", "confidence": 0.0,
            "matches_expected": False, "needs_human_review": True,
            "raw_response": content[:500],
        }

    @staticmethod
    def _validate_action_result(data: dict) -> dict:
        return {
            "action": str(data.get("action", "unknown")),
            "confidence": min(1.0, max(0.0, float(data.get("confidence", 0.0)))),
            "matches_expected": bool(data.get("matches_expected", False)),
            "details": str(data.get("details", "")),
        }
