"""多模态大模型推理客户端（通过 Ollama API）

优化策略：
- 超时 60s 适配 7B 模型本地推理
- 图片压缩到 480px 降低传输和推理开销
- keep_alive 保持模型常驻 GPU/内存
- JPEG 质量 70% 减小 payload
"""

import base64
import json
import re

import cv2
import httpx
import numpy as np
from loguru import logger

_MAX_IMAGE_DIM = 480
_JPEG_QUALITY = 70


class VLMClient:

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-vl:7b",
        timeout: float = 60.0,
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
        images_b64 = [self._frame_to_base64(f) for f in frames[-1:]]
        prompt = self._build_prompt(sop_context)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt, "images": images_b64}],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 200},
            "keep_alive": "30m",
        }
        try:
            resp = self.client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            result = resp.json()
            return self._parse_response(self._extract_message_content(result))
        except Exception as e:
            logger.error("VLM 推理失败: {}", e)
            return {"action": "unknown", "confidence": 0.0, "description": str(e)}

    @staticmethod
    def _extract_message_content(result: dict) -> str:
        msg = result.get("message")
        if isinstance(msg, dict):
            return str(msg.get("content", ""))
        if isinstance(msg, str):
            return msg
        return ""

    def classify_action_with_retry(self, frames: list, sop_context: dict, max_retries: int = 2) -> dict:
        for attempt in range(max_retries + 1):
            result = self.classify_action(frames, sop_context)
            if not result.get("needs_human_review"):
                return result
            if attempt < max_retries:
                logger.info("VLM 解析失败，重试 {}/{}", attempt + 1, max_retries)
        return result

    @staticmethod
    def _frame_to_base64(frame: np.ndarray) -> str:
        h, w = frame.shape[:2]
        if max(h, w) > _MAX_IMAGE_DIM:
            scale = _MAX_IMAGE_DIM / max(h, w)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
        return base64.b64encode(buffer).decode("utf-8")

    def _build_prompt(self, ctx: dict) -> str:
        current = ctx.get("current_step_index", 0)
        steps = ctx.get("steps", [])
        expected = steps[current].get("name", "未知") if current < len(steps) else "未知"
        expected_desc = steps[current].get("description", "") if current < len(steps) else ""
        return (
            f"你是 SOP 动作识别专家。当前期望步骤（第{current + 1}步）：{expected}\n"
            f"描述：{expected_desc}\n\n"
            "请判断图片中操作员是否在执行这个步骤。\n"
            '返回 JSON：{{"action": "动作描述", "matches_expected": true/false, "confidence": 0.0-1.0}}\n'
            "仅返回 JSON。"
        )

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
        logger.warning("VLM 响应解析失败: {}", content[:200])
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
