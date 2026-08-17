"""多模态大模型推理客户端（通过 Ollama API）

优化策略：
- 超时 60s 适配 7B 模型本地推理
- 多帧拼成时序网格图，让模型能判别动作演进而非静态姿势
- 步骤参考图作为视觉锚点与当前画面对比，减少对文字描述的依赖
- place / pick / screw / assemble 等结果态步骤只看当前帧，避免把位移误读成已完成
- keep_alive 保持模型常驻 GPU/内存
- JPEG 压缩控制 payload
"""

import base64
import binascii
import json
import re

import cv2
import httpx
import numpy as np
from loguru import logger

from src.inference.frame_policy import is_assembly_step, is_release_step, is_transition_step

_MAX_IMAGE_DIM = 480
# 2×2 网格取 2 倍单帧上限，使每格分辨率与原先单帧持平，
# 换取时序信息而不牺牲螺丝、卡扣这类小目标的可辨识度
_GRID_MAX_DIM = _MAX_IMAGE_DIM * 2
_REFERENCE_MAX_DIM = 480
_JPEG_QUALITY = 70
_GRID_LABEL_COLOR = (0, 255, 255)
_GRID_BORDER_COLOR = (255, 255, 255)
_REFERENCE_CACHE_LIMIT = 32


class VLMClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3-vl:8b-instruct",
        timeout: float = 60.0,
        num_ctx: int = 2048,
        use_reference_frame: bool = True,
        temperature: float = 0.1,
    ) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.use_reference_frame = use_reference_frame
        # trust_env=False 绕开系统/环境代理：Ollama 跑在本机，走代理会被拦成 502，
        # 而失败结果与「动作不匹配」长得一样，现场只会表现为 SOP 永远不推进
        self.client = httpx.Client(timeout=timeout, trust_env=False)
        self._reference_cache: dict[str, str] = {}

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def classify_action(self, frames: list[np.ndarray], sop_context: dict) -> dict:
        if not frames:
            return {"action": "unknown", "confidence": 0.0, "idle": True, "description": "无输入帧"}

        sequence_b64, frame_count = self._encode_sequence(frames)
        reference_b64 = self._reference_image(sop_context)
        # 参考图在前，模型按出现顺序引用；prompt 中的编号必须与此一致
        images_b64 = ([reference_b64] if reference_b64 else []) + [sequence_b64]
        prompt = self._build_prompt(
            sop_context,
            frame_count=frame_count,
            has_reference=bool(reference_b64),
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt, "images": images_b64}],
            "stream": False,
            "options": {"temperature": self.temperature, "num_predict": 200, "num_ctx": self.num_ctx},
            "keep_alive": "30m",
        }
        try:
            resp = self.client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            result = resp.json()
            return self._parse_response(self._extract_message_content(result))
        except Exception as e:
            logger.error("VLM 推理失败: {}", e)
            # error 字段让调用方能把「推理没跑成」和「跑成了但判否」区分开
            return {
                "action": "unknown",
                "confidence": 0.0,
                "matches_expected": False,
                "idle": True,
                "description": str(e),
                "error": str(e),
            }

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
    def _frame_to_base64(frame: np.ndarray, max_dim: int = _MAX_IMAGE_DIM) -> str:
        h, w = frame.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
        return base64.b64encode(buffer).decode("utf-8")

    def _encode_sequence(self, frames: list[np.ndarray]) -> tuple[str, int]:
        """把时序帧编码为单张图。单帧直接编码，多帧拼成带序号的网格。"""
        usable = [f for f in frames if f is not None and getattr(f, "size", 0) > 0]
        if not usable:
            return self._frame_to_base64(frames[-1]), 1
        if len(usable) == 1:
            return self._frame_to_base64(usable[0]), 1
        montage = self._build_montage(usable)
        return self._frame_to_base64(montage, max_dim=_GRID_MAX_DIM), len(usable)

    @staticmethod
    def _build_montage(frames: list[np.ndarray]) -> np.ndarray:
        """按时间顺序拼接为网格图，左上角标注序号供模型判断动作方向。

        统一使用单图而非多图输入：Ollama 各 VLM 对多图顺序的理解稳定性不一，
        而网格图把时序信息编码进空间布局，兼容性和 token 开销都更可控。
        """
        count = len(frames)
        cols = 2 if count > 2 else count
        rows = (count + cols - 1) // cols

        cell_h = min(f.shape[0] for f in frames)
        cell_w = min(f.shape[1] for f in frames)
        cells = []
        for i, frame in enumerate(frames):
            cell = cv2.resize(frame, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
            if cell.ndim == 2:
                cell = cv2.cvtColor(cell, cv2.COLOR_GRAY2BGR)
            cell = cell.copy()
            label_scale = max(0.6, cell_h / 480.0)
            cv2.putText(
                cell,
                str(i + 1),
                (12, int(16 + 30 * label_scale)),
                cv2.FONT_HERSHEY_SIMPLEX,
                label_scale,
                _GRID_LABEL_COLOR,
                max(2, int(2 * label_scale)),
                cv2.LINE_AA,
            )
            cv2.rectangle(cell, (0, 0), (cell_w - 1, cell_h - 1), _GRID_BORDER_COLOR, 2)
            cells.append(cell)

        blank = np.zeros((cell_h, cell_w, 3), dtype=cells[0].dtype)
        cells.extend(blank for _ in range(rows * cols - count))
        return np.vstack([np.hstack(cells[r * cols : (r + 1) * cols]) for r in range(rows)])

    def _reference_image(self, ctx: dict) -> str:
        """取当前步骤的参考图并归一化尺寸。无参考图或解码失败时返回空串。"""
        if not self.use_reference_frame or ctx.get("global_detect"):
            return ""
        steps = ctx.get("steps", [])
        current = ctx.get("current_step_index", 0)
        if not isinstance(current, int) or not 0 <= current < len(steps):
            return ""
        raw = str(steps[current].get("reference_frame_b64") or "").strip()
        if not raw:
            return ""
        if "," in raw and raw.lstrip().startswith("data:"):
            raw = raw.split(",", 1)[1]

        cached = self._reference_cache.get(raw)
        if cached is not None:
            return cached

        normalized = self._normalize_reference(raw)
        if len(self._reference_cache) >= _REFERENCE_CACHE_LIMIT:
            self._reference_cache.clear()
        self._reference_cache[raw] = normalized
        return normalized

    @staticmethod
    def _normalize_reference(raw_b64: str) -> str:
        """重新压缩参考图以控制 payload；解码失败返回空串而非中断推理。"""
        try:
            buf = np.frombuffer(base64.b64decode(raw_b64, validate=True), dtype=np.uint8)
        except (binascii.Error, ValueError) as e:
            logger.warning("步骤参考图 base64 解码失败，本次跳过参考图: {}", e)
            return ""
        image = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if image is None:
            logger.warning("步骤参考图无法解码为图像，本次跳过参考图")
            return ""
        return VLMClient._frame_to_base64(image, max_dim=_REFERENCE_MAX_DIM)

    def _build_prompt(
        self,
        ctx: dict,
        *,
        frame_count: int = 1,
        has_reference: bool = False,
    ) -> str:
        if ctx.get("global_detect"):
            return self._build_global_prompt(ctx, frame_count=frame_count)
        current = ctx.get("current_step_index", 0)
        steps = ctx.get("steps", [])
        step = steps[current] if current < len(steps) else {}
        expected = step.get("name", "未知")
        step_detail = self._format_step_detail(step)
        action_type = str(step.get("action_type") or "")
        type_rule = ""
        if is_release_step(action_type):
            type_rule = "- 放置/脱手类以结果状态为准：物件仍在手里时必须 false，正在移动手中物件不算完成\n"
        elif is_transition_step(action_type):
            type_rule = (
                "- 取拿类看结果态：手已握住目标物件，且物件正在离开或已经离开原位，即为 true。"
                "已经握稳但还在当前步骤，仍应 true，不要改成 idle；"
                "物件仍完全静置原位、尚未被握住，才是 idle\n"
            )
        elif is_assembly_step(action_type):
            type_rule = (
                "- 拧紧/组装类看结果态：当前画面已满足 OK 判定才为 true（如螺丝已拧到位且工具离开，"
                "或零件已贴合定位）。工具正在对准、零件悬在上方、或仅有旋转靠近，都还是 idle\n"
            )
        return (
            f"你是SOP动作验证专家。当前期望步骤：{expected}\n"
            f"{step_detail}\n\n"
            "先根据画面如实描述操作员和物件此刻在哪里，再对照期望步骤判定。"
            "禁止为了迎合期望步骤，描述或认定画面中没有发生的动作。\n\n"
            f"{self._describe_images(frame_count, has_reference)}\n"
            f"{self._sequence_guidance(frame_count, has_reference, action_type)}"
            "判定规则：\n"
            f"{type_rule}"
            "- matches_expected=true: 操作员正在主动执行该步骤的核心动作（手部有明确的操作行为）\n"
            "- 如果画面已经满足 OK 判定，也可返回 matches_expected=true，此时 idle 必须为 false\n"
            "- idle=true: 操作员在等待、观察或尚未开始，没有做错。等待不是错误，不得因此判 NG\n"
            "- idle=false 且 matches_expected=false: 还没对齐期望步骤，但若没有缺陷，ng_violation 必须为 false\n"
            "- ng_violation=true: 画面出现 NG 判定里的真正缺陷（拿错、放错、掉落、损坏）。仅此时才算做错\n"
            "- 必选对象未出现且没有错误操作时，应返回 idle=true，ng_violation=false\n"
            "注意：仅仅站在工位前、看着设备、或手放在设备附近不算在执行步骤，应返回 idle=true。\n"
            "不要因为动作还没发生、或发生得比预想慢，就判成错误。\n"
            "NG 判定只描述缺陷。尚未开始、仍在等待、或正在做下一步之前的准备，一律 idle=true 且 ng_violation=false。\n\n"
            "只返回JSON，格式如下：\n"
            '{"action": "<描述你看到的具体动作>", "matches_expected": true或false, "idle": true或false, "ng_violation": true或false, "confidence": 0.0到1.0}'
        )

    @staticmethod
    def _describe_images(frame_count: int, has_reference: bool) -> str:
        """说明每张输入图的含义，编号需与 classify_action 的 images 顺序一致。"""
        lines = []
        idx = 1
        if has_reference:
            lines.append(f"图{idx}：该步骤的标准参考画面（正确完成时的样子）。")
            idx += 1
        if frame_count > 1:
            lines.append(
                f"图{idx}：当前工位的连续画面，按时间先后拼成网格，"
                f"左上角数字 1~{frame_count} 表示时间顺序（1 最早，{frame_count} 最新）。"
            )
        else:
            lines.append(f"图{idx}：当前工位画面。")
        return "\n".join(lines)

    @staticmethod
    def _sequence_guidance(frame_count: int, has_reference: bool, action_type: str = "") -> str:
        parts = []
        if is_release_step(action_type):
            # 期望步骤写着「放下」会构成确认偏置；多帧位移更容易被读成完成。
            # 这里强制先看当前状态：物件是否已经脱手，而不是推断运动意图。
            parts.append(
                "此步骤是「放置/脱手」类判定。先看物件此刻在哪里、手是否握住，"
                "再对照期望步骤；不要因为当前期望是「放下」就把位移解释为放下。\n"
                "必须在当前画面中直接看到物件已经离开手并处于目标位置才判 true。"
                "手中物件的高度、角度或朝向变化都不能视为已放下；"
                "只要物件仍被握住，必须判 false。\n"
            )
        elif is_transition_step(action_type):
            parts.append(
                "此步骤是「取拿」结果态判定。看当前画面：目标物件是否已被手握住，"
                "并且不再完全静置在原来的位置（正在抬离或已经离开都算）。\n"
                "若已经握在手里并离开原位，即使动作已经停住，也必须判 true——"
                "这表示取拿已经完成，不要因为握稳就改成 idle。\n"
                "只有还没握住、物件仍在原位静置时，才判 idle=true。\n"
            )
        elif is_assembly_step(action_type):
            parts.append(
                "此步骤是「拧紧/组装」结果态判定。必须在当前画面直接看到已经就位："
                "螺丝拧到位且工具离开孔位，或零件已进入治具并贴合定位边。\n"
                "不要因为电批在转、手在按、或零件正在靠近，就推断已经完成。"
                "悬停、对准、旋转中都还不算，应 idle=true。\n"
                "已经就位后即使动作停住，仍应判 true。\n"
            )
        elif frame_count > 1:
            parts.append(
                f"判定以第{frame_count}格（最新一格）的画面为准，它代表当前状态；"
                "前面几格只用来看清动作正朝哪个方向进行，不能替代当前状态。\n"
                "只有当最新一格里能直接看到该步骤的结果状态时才判 true。"
                "序列中出现移动或姿态变化，不等于动作已经完成——物件在手中改变"
                "高度或角度，不能据此推断它已被放下、装上或取走。\n"
                "画面静止不代表没有执行：若该步骤本身就是保持某种状态，"
                "只要最新一格符合 OK 判据就判 true。\n"
            )
        if has_reference:
            parts.append("把最新画面与标准参考画面对比，以画面实际差异为准，不要仅依据文字描述推测。\n")
        if not parts:
            parts.append("仔细观察图片中操作员正在执行的具体动作。\n")
        return "".join(parts)

    def _build_global_prompt(self, ctx: dict, *, frame_count: int = 1) -> str:
        steps = ctx.get("steps", [])
        completed = set(ctx.get("completed_indices", []))
        remaining = []
        for i, s in enumerate(steps):
            if i not in completed:
                name = s.get("name", f"步骤{i + 1}")
                desc = s.get("description", "")
                ok = s.get("ok_criteria", "")
                ng = s.get("ng_criteria", "")
                detail = f" ({desc})" if desc else ""
                criteria = ""
                if ok:
                    criteria += f"；OK: {ok}"
                if ng:
                    criteria += f"；NG: {ng}"
                remaining.append(f"  {i}: {name}{detail}{criteria}")
        steps_text = "\n".join(remaining) if remaining else "  (所有步骤已完成)"
        sequence_note = (
            f"画面是当前工位的连续帧，按时间先后拼成网格，左上角数字 1~{frame_count} "
            f"表示时间顺序（1 最早，{frame_count} 最新）。判定以第{frame_count}格为准，"
            "它代表当前状态，前面几格只用来看清动作方向。只有最新一格里能直接看到"
            "某步骤的结果状态时才匹配该步骤；序列中的移动或姿态变化不等于动作已完成。\n"
            if frame_count > 1
            else ""
        )
        return (
            "你是 SOP 动作验证专家。以下是尚未完成的 SOP 步骤：\n"
            f"{steps_text}\n\n"
            f"{sequence_note}"
            "仔细观察图片，操作员正在执行哪个步骤？\n"
            "如果操作员正在执行其中某个步骤，返回该步骤编号；否则返回 -1。\n"
            "只返回 JSON，格式如下：\n"
            '{"action": "<描述你看到的动作>", "matched_step": <步骤编号或-1>, "confidence": <0.0到1.0>}'
        )

    @staticmethod
    def _format_step_detail(step: dict) -> str:
        lines = []
        description = str(step.get("description") or "").strip()
        action_type = str(step.get("action_type") or "").strip()
        required_objects = step.get("required_objects") or []
        ok_criteria = str(step.get("ok_criteria") or "").strip()
        ng_criteria = str(step.get("ng_criteria") or "").strip()

        if description:
            lines.append(f"说明：{description}")
        if action_type:
            lines.append(f"动作类型：{action_type}")
        if required_objects:
            objects = "、".join(str(o) for o in required_objects if str(o).strip())
            if objects:
                lines.append(f"必选对象：{objects}")
        if ok_criteria:
            lines.append(f"OK 判定：{ok_criteria}")
        if ng_criteria:
            lines.append(f"NG 判定：{ng_criteria}")
        return "\n".join(lines) if lines else "说明：无"

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
            "action": "parse_failed",
            "confidence": 0.0,
            "matches_expected": False,
            "idle": True,
            "needs_human_review": True,
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
        if "idle" in data:
            idle = bool(data.get("idle"))
        else:
            # 模型常漏写 idle：未匹配默认当等待，避免把「还没做」停线
            idle = not matches
        if matches:
            idle = False
        ng_violation = bool(data.get("ng_violation", False))
        if matches:
            ng_violation = False
        return {
            "action": action,
            "confidence": confidence,
            "matches_expected": matches,
            "idle": idle,
            "ng_violation": ng_violation,
            "details": str(data.get("details", "")),
        }
