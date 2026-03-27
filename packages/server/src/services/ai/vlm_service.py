"""VLM 视觉语言分析服务 — 通过 Ollama API 调用 Qwen2.5-VL"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Callable

import cv2
import httpx
import numpy as np
from loguru import logger


class VLMService:
    """通过 Ollama HTTP API 调用视觉语言模型，分析制造操作视频帧。"""

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "qwen2.5vl:3b",
        timeout: float = 120.0,
        max_retries: int = 2,
    ):
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def check_available(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get(f"{self.ollama_url}/api/tags", timeout=5.0)
            if resp.status_code != 200:
                return False
            data = resp.json()
            model_names = [m.get("name", "") for m in data.get("models", [])]
            available = any(self.model in name for name in model_names)
            if not available:
                logger.warning("VLM 模型 {} 未找到，已安装: {}", self.model, model_names)
            return available
        except Exception as e:
            logger.error("无法连接 Ollama: {}", e)
            return False

    async def analyze_overview(
        self,
        frames: list[np.ndarray],
        process_name: str,
    ) -> str:
        """发送少量帧，获取工序整体概览描述。"""
        images_b64 = [self._encode_frame(f) for f in frames[:5]]

        prompt = (
            f"这是一段「{process_name}」工业制造工序的操作视频截图（按时间顺序排列）。\n"
            "请概述这段操作的整体流程，包括：\n"
            "1. 操作员大致在做什么\n"
            "2. 使用了哪些工具或物料\n"
            "3. 大约分为几个主要阶段\n"
            "用简洁的中文回答。"
        )

        return await self._chat(prompt, images_b64)

    async def analyze_steps(
        self,
        frames: list[np.ndarray],
        timestamps: list[float],
        detected_objects_per_frame: list[list[str]],
        process_name: str,
        overview: str,
        on_batch_progress: Callable[[int, int], None] | None = None,
    ) -> list[dict]:
        """分批分析帧序列，识别具体操作步骤并输出结构化 JSON。"""
        batch_size = 5
        all_raw_steps: list[dict] = []
        total_batches = (len(frames) + batch_size - 1) // batch_size

        for batch_idx, batch_start in enumerate(range(0, len(frames), batch_size)):
            batch_end = min(batch_start + batch_size, len(frames))
            batch_frames = frames[batch_start:batch_end]
            batch_timestamps = timestamps[batch_start:batch_end]
            batch_objects = detected_objects_per_frame[batch_start:batch_end]

            if on_batch_progress:
                on_batch_progress(batch_idx, total_batches)

            images_b64 = [self._encode_frame(f) for f in batch_frames]

            obj_desc = ""
            for i, (ts, objs) in enumerate(zip(batch_timestamps, batch_objects)):
                if objs:
                    obj_desc += f"  帧 {batch_start + i + 1} (t={ts:.1f}s): 检测到 {', '.join(objs)}\n"

            prompt = (
                f"工序「{process_name}」的操作视频分析。\n"
                f"整体概览：{overview}\n\n"
                f"以下是第 {batch_start + 1}~{batch_end} 帧的截图（按时间顺序）。\n"
            )
            if obj_desc:
                prompt += f"YOLO 目标检测结果：\n{obj_desc}\n"

            prompt += (
                "请识别这组帧中包含的操作步骤，返回 JSON 数组。\n"
                "每个步骤格式：\n"
                '{"name": "步骤名", "description": "详细描述", '
                '"action_type": "动作类型(pick_up/position/assemble/fasten/inspect/scan/apply/insert/solder/test/pack/label/other)", '
                '"required_objects": ["物体1", "物体2"], '
                '"start_time": 起始秒数, "end_time": 结束秒数}\n\n'
                "规则：\n"
                "- 如果这组帧中没有明显的新步骤，返回空数组 []\n"
                "- 步骤名用简短中文\n"
                "- 仅返回 JSON 数组，不要其他文字"
            )

            try:
                raw = await self._chat(prompt, images_b64)
                steps = self._parse_steps_json(raw)
                all_raw_steps.extend(steps)
                logger.debug("VLM 批次 {}/{}: 识别 {} 个步骤", batch_idx + 1, total_batches, len(steps))
            except Exception as e:
                logger.warning("VLM 批次 {}/{} 分析失败: {}", batch_idx + 1, total_batches, e)

        return self._deduplicate_steps(all_raw_steps)

    async def refine_steps(
        self,
        steps: list[dict],
        process_name: str,
        overview: str,
    ) -> list[dict]:
        """用纯文本模式对步骤列表进行优化和补全。"""
        steps_json = json.dumps(steps, ensure_ascii=False, indent=2)
        prompt = (
            f"工序「{process_name}」的 SOP 步骤列表如下：\n"
            f"```json\n{steps_json}\n```\n\n"
            f"整体概览：{overview}\n\n"
            "请优化这些步骤：\n"
            "1. 合并重复或过于相似的步骤\n"
            "2. 补充缺失的判定标准 ok_criteria 和 ng_criteria\n"
            "3. 为每个步骤添加合理的 timeout_seconds（秒）\n"
            "4. 标记可选步骤 is_optional: true/false\n"
            "5. 确保步骤顺序合理\n\n"
            "输出格式（JSON 数组）：\n"
            '[{"index": 0, "name": "步骤名", "description": "描述", '
            '"action_type": "类型", "required_objects": ["..."], '
            '"timeout_seconds": 30, "is_optional": false, '
            '"ok_criteria": "合格标准", "ng_criteria": "不合格标准"}]\n\n'
            "仅返回 JSON 数组。"
        )

        raw = await self._chat(prompt, [])
        refined = self._parse_steps_json(raw)

        if not refined:
            logger.warning("VLM 步骤优化返回空结果，保留原始步骤")
            return steps

        for i, step in enumerate(refined):
            step["index"] = i
            step.setdefault("timeout_seconds", 30)
            step.setdefault("is_optional", False)
            step.setdefault("ok_criteria", "")
            step.setdefault("ng_criteria", "")
            step.setdefault("reference_frame_url", "")

        return refined

    async def _chat(self, prompt: str, images_b64: list[str]) -> str:
        message: dict = {"role": "user", "content": prompt}
        if images_b64:
            message["images"] = images_b64

        payload = {
            "model": self.model,
            "messages": [message],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 2000},
        }

        client = await self._get_client()
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 2):
            try:
                resp = await client.post(f"{self.ollama_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["message"]["content"]
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_exc = e
                if attempt <= self.max_retries:
                    wait = 2 ** attempt
                    logger.warning("VLM 请求失败 (第{}次), {}秒后重试: {}", attempt, wait, e)
                    await asyncio.sleep(wait)
        raise last_exc  # type: ignore[misc]

    @staticmethod
    def _encode_frame(frame: np.ndarray) -> str:
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return base64.b64encode(buffer).decode("utf-8")

    @staticmethod
    def _parse_steps_json(raw: str) -> list[dict]:
        content = raw.strip()
        if "```" in content:
            parts = content.split("```")
            for part in parts[1:]:
                lines = part.strip().split("\n", 1)
                if len(lines) == 2:
                    content = lines[1].rsplit("```", 1)[0]
                    break
                elif len(lines) == 1:
                    content = lines[0].rsplit("```", 1)[0]
                    break

        content = content.strip()
        if not content.startswith("["):
            start = content.find("[")
            if start != -1:
                content = content[start:]

        try:
            result = json.loads(content)
            if isinstance(result, list):
                return result
            return []
        except json.JSONDecodeError:
            logger.warning("VLM 返回内容无法解析为 JSON: {}...", content[:200])
            return []

    @staticmethod
    def _deduplicate_steps(steps: list[dict]) -> list[dict]:
        if not steps:
            return []

        unique: list[dict] = [steps[0]]
        for step in steps[1:]:
            last = unique[-1]
            if step.get("name") == last.get("name") and step.get("action_type") == last.get("action_type"):
                continue
            unique.append(step)

        return unique
