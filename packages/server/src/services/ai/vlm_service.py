"""VLM 视觉语言分析服务 — 通过 Ollama API 调用 Qwen2.5-VL"""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Awaitable, Callable

import cv2
import httpx
import numpy as np
from loguru import logger


class VLMService:
    """通过 Ollama HTTP API 调用视觉语言模型，分析制造操作视频帧。"""

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "qwen2.5-vl:7b",
        timeout: float = 300.0,
        max_retries: int = 3,
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
        images_b64 = [self._encode_frame(f) for f in frames[:3]]

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
        on_batch_progress: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> list[dict]:
        """两阶段步骤识别：先用全局视角获取步骤列表，再逐批补充细节。"""

        # --- 阶段 A：全局步骤识别 ---
        # 均匀采样最多 8 帧，确保覆盖视频全程
        n_samples = min(8, len(frames))
        if n_samples <= 1:
            sample_indices = [0]
        else:
            sample_indices = [round(i * (len(frames) - 1) / (n_samples - 1)) for i in range(n_samples)]
        sample_indices = sorted(set(sample_indices))
        sample_frames = [frames[i] for i in sample_indices]
        sample_images = [self._encode_frame(f) for f in sample_frames]

        all_objects: set[str] = set()
        for objs in detected_objects_per_frame:
            all_objects.update(objs)

        global_prompt = (
            f"这是「{process_name}」工序的操作视频，共 {len(sample_indices)} 张关键帧截图（按时间顺序排列）。\n"
            f"操作概览：{overview}\n"
        )
        if all_objects:
            global_prompt += f"视频中出现的物体：{', '.join(sorted(all_objects))}\n"
        global_prompt += (
            "\n请仔细观察每一帧画面之间的变化，尽可能详细地列出所有操作步骤。\n"
            "要求：\n"
            "1. 每个步骤写一行，格式为：步骤编号. 步骤名称 - 详细描述\n"
            "2. 每个独立的动作都应该作为一个单独的步骤\n"
            "3. 把每一帧中看到的新动作或状态变化都列为步骤\n"
            "4. 包含准备、取料、操作、放置、检查等各个阶段\n"
            "5. 用简短中文描述\n"
            "6. 只写步骤列表，不要写其他内容\n\n"
            "示例：\n"
            "1. 准备工位 - 检查工位清洁度，确认工具齐全\n"
            "2. 取出物料 - 从料盒中取出 PCB 板\n"
            "3. 定位放置 - 将 PCB 放到治具上对准定位孔\n"
            "4. 拿取工具 - 从工具架拿起电动螺丝刀\n"
            "5. 拧第一颗螺丝 - 对准螺丝孔拧入螺丝并拧紧\n"
            "6. 拧第二颗螺丝 - 移到第二个螺丝孔拧入并拧紧\n"
            "7. 放回工具 - 将螺丝刀放回工具架\n"
            "8. 目视检查 - 确认所有螺丝是否拧紧到位\n"
        )

        if on_batch_progress:
            await on_batch_progress(0, 2)

        try:
            global_raw = await self._chat(global_prompt, sample_images)
            logger.info("VLM 全局步骤识别原文: {}", global_raw[:500])
            global_steps = self._parse_text_steps(global_raw, all_objects)
        except Exception as e:
            logger.warning("VLM 全局步骤识别失败: {}", e)
            global_steps = []

        if on_batch_progress:
            await on_batch_progress(1, 2)

        if not global_steps:
            logger.warning("VLM 全局步骤识别返回空，尝试 JSON 模式")
            global_steps = await self._fallback_json_steps(
                sample_images, process_name, overview, all_objects,
            )

        logger.info("VLM 步骤识别完成: {} 个步骤", len(global_steps))
        return self._deduplicate_steps(global_steps)

    async def _fallback_json_steps(
        self,
        images_b64: list[str],
        process_name: str,
        overview: str,
        all_objects: set[str],
    ) -> list[dict]:
        """JSON 格式的备用步骤提取。"""
        prompt = (
            f"工序「{process_name}」视频分析。\n"
            f"概览：{overview}\n"
        )
        if all_objects:
            prompt += f"检测到的物体：{', '.join(sorted(all_objects))}\n"
        prompt += (
            "\n请输出操作步骤 JSON 数组：\n"
            '[{"name": "步骤名", "description": "描述"}]\n'
            "仅输出 JSON。"
        )
        try:
            raw = await self._chat(prompt, images_b64)
            return self._parse_steps_json(raw)
        except Exception as e:
            logger.warning("VLM JSON 备用模式也失败: {}", e)
            return []

    @staticmethod
    def _parse_text_steps(raw: str, all_objects: set[str] | None = None) -> list[dict]:
        """解析自然语言步骤列表（兼容 '1. 步骤名 - 描述' 格式）。"""
        import re
        steps = []
        for line in raw.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(\d+)[.、)\]]\s*(.+)", line)
            if not m:
                continue
            text = m.group(2).strip()
            if " - " in text:
                name, desc = text.split(" - ", 1)
            elif "：" in text:
                name, desc = text.split("：", 1)
            elif ":" in text:
                name, desc = text.split(":", 1)
            else:
                name, desc = text, ""

            name = name.strip()
            desc = desc.strip()
            if not name:
                continue

            required_objects = []
            if all_objects:
                for obj in all_objects:
                    if obj.lower() in (name + desc).lower():
                        required_objects.append(obj)

            steps.append({
                "name": name,
                "description": desc,
                "action_type": "other",
                "required_objects": required_objects,
            })
        return steps

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
            "1. 补充缺失的判定标准 ok_criteria 和 ng_criteria\n"
            "2. 为每个步骤添加合理的 timeout_seconds（秒）\n"
            "3. 标记可选步骤 is_optional: true/false\n"
            "4. 确保步骤顺序合理\n"
            "5. 如果概览中提到了额外的操作阶段但步骤中没有，请补充\n\n"
            "重要：不要合并现有步骤，保留所有已识别的步骤。\n\n"
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
            except httpx.HTTPStatusError as e:
                last_exc = e
                if e.response.status_code >= 500 and attempt <= self.max_retries:
                    wait = 2 ** attempt
                    logger.warning(
                        "VLM 请求失败 (HTTP {} 第{}次), {}秒后重试: {}",
                        e.response.status_code,
                        attempt,
                        wait,
                        e,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_exc = e
                if attempt <= self.max_retries:
                    wait = 2 ** attempt
                    logger.warning("VLM 请求失败 (第{}次), {}秒后重试: {}", attempt, wait, e)
                    await asyncio.sleep(wait)
        raise last_exc  # type: ignore[misc]

    @staticmethod
    def _encode_frame(frame: np.ndarray, max_dim: int = 640) -> str:
        h, w = frame.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
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
