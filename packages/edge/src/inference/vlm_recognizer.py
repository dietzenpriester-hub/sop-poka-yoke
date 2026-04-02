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
        model: str = "qwen3-vl:8b-instruct",
        timeout: float = 60.0,
        num_ctx: int = 2048,
    ) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.num_ctx = num_ctx
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
            "options": {"temperature": 0.1, "num_predict": 200, "num_ctx": self.num_ctx},
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
        if ctx.get("global_detect"):
            return self._build_global_prompt(ctx)
        current = ctx.get("current_step_index", 0)
        steps = ctx.get("steps", [])
        expected = steps[current].get("name", "未知") if current < len(steps) else "未知"
        expected_desc = steps[current].get("description", "") if current < len(steps) else ""
        desc_line = f"\n说明：{expected_desc}" if expected_desc else ""
        return (
            f"你是SOP动作验证专家。当前期望步骤：{expected}{desc_line}\n\n"
            "仔细观察图片中操作员正在执行的具体动作。\n"
            "判定规则：\n"
            "- matches_expected=true: 操作员正在主动执行该步骤的核心动作（手部有明确的操作行为）\n"
            "- matches_expected=false: 操作员处于等待、观察、空闲状态，或在执行其他不相关的操作\n"
            "注意：仅仅站在工位前、看着设备、或手放在设备附近不算在执行步骤。\n\n"
            "只返回JSON，格式如下：\n"
            '{"action": "<描述你看到的具体动作>", "matches_expected": true或false, "confidence": 0.0到1.0}'
        )

    def _build_global_prompt(self, ctx: dict) -> str:
        steps = ctx.get("steps", [])
        completed = set(ctx.get("completed_indices", []))
        remaining = []
        for i, s in enumerate(steps):
            if i not in completed:
                name = s.get("name", f"步骤{i + 1}")
                desc = s.get("description", "")
                remaining.append(f"  {i}: {name}" + (f" ({desc})" if desc else ""))
        steps_text = "\n".join(remaining) if remaining else "  (所有步骤已完成)"
        return (
            "你是 SOP 动作验证专家。以下是尚未完成的 SOP 步骤：\n"
            f"{steps_text}\n\n"
            "仔细观察图片，操作员正在执行哪个步骤？\n"
            "如果操作员正在执行其中某个步骤，返回该步骤编号；否则返回 -1。\n"
            "只返回 JSON，格式如下：\n"
            '{"action": "<描述你看到的动作>", "matched_step": <步骤编号或-1>, "confidence": <0.0到1.0>}'
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

    _INVALID_ACTIONS = {"动作描述", "describe what you actually see", "unknown", ""}

    @classmethod
    def _validate_action_result(cls, data: dict) -> dict:
        action = str(data.get("action", "unknown")).strip()
        confidence = min(1.0, max(0.0, float(data.get("confidence", 0.0))))
        if action in cls._INVALID_ACTIONS:
            confidence = 0.0

        if "matched_step" in data:
            matched_step = int(data.get("matched_step", -1))
            return {
                "action": action,
                "confidence": confidence,
                "matched_step": matched_step,
                "matches_expected": matched_step >= 0,
                "details": str(data.get("details", "")),
            }

        matches = bool(data.get("matches_expected", False))
        if action in cls._INVALID_ACTIONS:
            matches = False
        return {
            "action": action,
            "confidence": confidence,
            "matches_expected": matches,
            "details": str(data.get("details", "")),
        }
