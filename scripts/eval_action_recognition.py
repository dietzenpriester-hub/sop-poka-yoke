"""动作识别准度离线评测。

把标注过的视频喂进与边缘端相同的感知组件（关键帧 → YOLO → VLM 门控 →
时序采样 → VLM → 状态机），输出可对比的准度指标。目的是让 prompt、时序窗口、
置信度阈值这类调整有客观依据，而不是靠现场感觉。

与 main.py 的区别只在于同步执行且不接 MQTT/Modbus/MJPEG：VLM 在这里阻塞调用，
保证每次判定都对应确定的帧序列，结果可复现。

指标：
- 判定级：每次 VLM 调用是否正确回答「当前画面是否在执行期望步骤」（二分类 P/R/F1）
- 步骤级：每个真值步骤是否被状态机判过，以及触发延迟
- 误触发：状态机在真值不成立时推进步骤的次数

用法：
    # 先用 annotate_timeline.py 生成并填好标注 CSV
    python scripts/eval_action_recognition.py \\
        --video data/clips/xxx.mp4 \\
        --timeline eval/annotations/xxx_timeline.csv \\
        --template eval/sop_template.json \\
        --label baseline

    # A/B 对比：关掉多帧与参考图，复现改造前的行为
    python scripts/eval_action_recognition.py ... --frame-window 1 --no-reference --label single-frame
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2

EDGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "edge"
sys.path.insert(0, str(EDGE_ROOT))

from src.capture.motion_detect import KeyframeExtractor  # noqa: E402
from src.capture.temporal_sampler import TemporalFrameSampler  # noqa: E402
from src.engine.state_machine import SOPStateMachine, SOPStatus  # noqa: E402
from src.engine.vlm_gate import VLMTriggerGate  # noqa: E402
from src.inference.frame_policy import select_frames_for_step  # noqa: E402
from src.inference.vlm_recognizer import VLMClient  # noqa: E402
from src.inference.yolo_detector import YOLODetector  # noqa: E402

IDLE_STEP = -1


@dataclass
class Interval:
    start: float
    end: float
    step_index: int
    step_name: str


@dataclass
class CallRecord:
    """单次 VLM 调用的评测记录。"""

    timestamp: float
    expected_step: int
    truth_step: int
    predicted_match: bool
    confidence: float
    action: str
    infer_ms: float
    frame_count: int
    fsm_event: str
    error: str = ""
    due: bool | None = None

    @property
    def should_match(self) -> bool:
        if self.due is not None:
            return self.due
        return self.truth_step == self.expected_step

    @property
    def outcome(self) -> str:
        if self.predicted_match and self.should_match:
            return "TP"
        if self.predicted_match and not self.should_match:
            return "FP"
        if not self.predicted_match and self.should_match:
            return "FN"
        return "TN"


@dataclass
class StepOutcome:
    step_index: int
    step_name: str
    truth_start: float
    truth_end: float
    triggered_at: float | None = None
    trigger_source: str = ""

    @property
    def latency(self) -> float | None:
        if self.triggered_at is None:
            return None
        return self.triggered_at - self.truth_start


@dataclass
class EvalConfig:
    frame_window: int
    frame_interval: float
    use_reference: bool
    min_confidence: float
    min_consecutive_pass: int
    ng_tolerance: int
    yolo_model: str
    vlm_model: str
    stride: int
    idle_max_seconds: float
    temperature: float
    gate_cooldown: float | None
    adaptive_window: bool = True
    truth_grace_seconds: float = 1.0
    extra: dict[str, Any] = field(default_factory=dict)


def resolve_yolo_model(name: str) -> str:
    """优先复用 packages/edge 下已有权重，避免评测时重复下载到仓库根目录。"""
    if Path(name).exists():
        return name
    bundled = EDGE_ROOT / name
    return str(bundled) if bundled.exists() else name


def load_timeline(path: Path) -> list[Interval]:
    intervals: list[Interval] = []
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not (row.get("start_sec") or "").strip():
                continue
            step_index = int(float(row.get("step_index", IDLE_STEP)))
            intervals.append(
                Interval(
                    start=float(row["start_sec"]),
                    end=float(row["end_sec"]),
                    step_index=step_index,
                    step_name=(row.get("step_name") or "").strip(),
                )
            )
    intervals.sort(key=lambda i: i.start)
    if not intervals:
        raise SystemExit(f"标注 CSV 中没有有效区间: {path}")
    return intervals


def truth_at(intervals: list[Interval], timestamp: float) -> int:
    for iv in intervals:
        if iv.start <= timestamp < iv.end:
            return iv.step_index
    return IDLE_STEP


def step_is_due(
    intervals: list[Interval],
    step_index: int,
    timestamp: float,
    grace_seconds: float = 0.0,
) -> bool:
    """当前步骤是否处于真值区间（含边界宽限）。

    防呆判的是动作对错，不是卡在某一秒发生。评测若按精确时间窗打分，
    模型早/晚 0.3 秒都会变成误报，和生产现场「做得慢一点」被停线是同一类问题。
    """
    for iv in intervals:
        if iv.step_index != step_index:
            continue
        if iv.start - grace_seconds <= timestamp < iv.end + grace_seconds:
            return True
    return False


def truth_steps(intervals: list[Interval]) -> list[StepOutcome]:
    """按步骤下标合并真值区间，同一步骤多段时取首段起点与末段终点。"""
    merged: dict[int, StepOutcome] = {}
    for iv in intervals:
        if iv.step_index == IDLE_STEP:
            continue
        existing = merged.get(iv.step_index)
        if existing is None:
            merged[iv.step_index] = StepOutcome(
                step_index=iv.step_index,
                step_name=iv.step_name,
                truth_start=iv.start,
                truth_end=iv.end,
            )
        else:
            existing.truth_start = min(existing.truth_start, iv.start)
            existing.truth_end = max(existing.truth_end, iv.end)
    return [merged[k] for k in sorted(merged)]


class MockVLM:
    """按真值作答的假 VLM，用于在没有 Ollama 时验证评测脚本本身。"""

    def __init__(self, intervals: list[Interval]) -> None:
        self._intervals = intervals
        self.timestamp = 0.0

    def classify_action(self, frames: list, sop_context: dict) -> dict:
        truth = truth_at(self._intervals, self.timestamp)
        expected = sop_context.get("current_step_index", 0)
        match = truth == expected
        return {
            "action": f"mock(truth={truth})",
            "matches_expected": match,
            "matched_step": truth,
            "idle": not match,
            "ng_violation": False,
            "confidence": 0.95 if match else 0.1,
        }

    def close(self) -> None:
        return None


def build_state_machine(
    template: dict, cfg: EvalConfig, global_detect: bool
) -> SOPStateMachine:
    fsm = SOPStateMachine(
        template,
        ng_tolerance=cfg.ng_tolerance,
        global_detect=global_detect,
        min_consecutive_pass=cfg.min_consecutive_pass,
    )
    fsm.MIN_CONFIDENCE = cfg.min_confidence
    return fsm


def replay(
    video: Path,
    intervals: list[Interval],
    template: dict,
    cfg: EvalConfig,
    *,
    vlm: Any,
    global_detect: bool,
    trace_path: Path | None,
) -> tuple[list[CallRecord], list[StepOutcome], dict[str, Any]]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"无法打开视频: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    motion = KeyframeExtractor()
    detector = YOLODetector(model_path=cfg.yolo_model)
    gate = VLMTriggerGate.from_env()
    if cfg.gate_cooldown is not None:
        gate.config.cooldown_seconds = cfg.gate_cooldown
    sampler = TemporalFrameSampler(
        window=cfg.frame_window, interval_seconds=cfg.frame_interval
    )
    fsm = build_state_machine(template, cfg, global_detect)
    fsm.start("EVAL-RUN")

    outcomes = truth_steps(intervals)
    by_index = {o.step_index: o for o in outcomes}
    calls: list[CallRecord] = []
    gate_reasons: Counter[str] = Counter()
    false_advances = 0
    keyframe_count = 0
    frame_index = 0
    last_submit_at = 0.0
    trace = open(trace_path, "w", encoding="utf-8") if trace_path else None

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_index += 1
            if cfg.stride > 1 and frame_index % cfg.stride:
                continue
            timestamp = frame_index / fps
            sampler.offer(frame, timestamp)

            is_keyframe = motion.is_keyframe(frame)
            keyframe_count += int(is_keyframe)
            if not is_keyframe:
                # 与 main.py 一致：静止画面下 VLM 空闲过久也强制判定一次，
                # 否则漏掉「该动却没动」这类超时/漏装场景
                if timestamp - last_submit_at < cfg.idle_max_seconds:
                    continue
                dets: list = []
                gate_reasons["idle_forced"] += 1
            else:
                dets = detector.detect(frame)
                # 用视频时间而非墙上时钟推进门控冷却，否则回放快于/慢于实时都会
                # 让 VLM 调用密度偏离产线实际，评测数字失去代表性
                decision = gate.should_submit(dets, frame.shape, now=timestamp)
                gate_reasons[decision.reason] += 1
                if not decision.allowed:
                    continue
            last_submit_at = timestamp

            expected_step = fsm.current_step_index
            sop_ctx = {
                "steps": [
                    {
                        "name": s.name,
                        "description": s.description,
                        "required_objects": s.required_objects,
                        "action_type": s.action_type,
                        "ok_criteria": s.ok_criteria,
                        "ng_criteria": s.ng_criteria,
                        "reference_frame_b64": s.reference_frame_b64,
                    }
                    for s in fsm.steps
                ],
                "current_step_index": expected_step,
            }
            if global_detect:
                sop_ctx["global_detect"] = True
                sop_ctx["completed_indices"] = list(fsm.completed_indices)

            if isinstance(vlm, MockVLM):
                vlm.timestamp = timestamp
            current_step = fsm.get_current_step()
            action_type = (
                current_step.action_type if current_step and not global_detect else ""
            )
            sequence = select_frames_for_step(
                action_type,
                sampler.snapshot() or [frame],
                frame,
                adaptive=cfg.adaptive_window,
            )
            t0 = time.perf_counter()
            action = vlm.classify_action(sequence, sop_ctx)
            infer_ms = (time.perf_counter() - t0) * 1000

            result = (
                fsm.process_global_action(action)
                if global_detect
                else fsm.process_action(action)
            )
            event = str(result.get("event", result.get("type", "")))

            record = CallRecord(
                timestamp=timestamp,
                expected_step=expected_step,
                truth_step=truth_at(intervals, timestamp),
                predicted_match=bool(action.get("matches_expected", False)),
                confidence=float(action.get("confidence", 0.0)),
                action=str(action.get("action", "")),
                infer_ms=infer_ms,
                frame_count=len(sequence),
                fsm_event=event,
                error=str(action.get("error", "")),
                due=step_is_due(
                    intervals,
                    expected_step,
                    timestamp,
                    cfg.truth_grace_seconds,
                ),
            )
            calls.append(record)
            if trace:
                trace.write(json.dumps(record.__dict__, ensure_ascii=False) + "\n")

            if event in {"step_ok", "complete"}:
                advanced = (
                    expected_step
                    if not global_detect
                    else int(action.get("matched_step", -1))
                )
                target = by_index.get(advanced)
                if target is not None and target.triggered_at is None:
                    target.triggered_at = timestamp
                    target.trigger_source = event
                if not record.should_match:
                    false_advances += 1
                sampler.reset()
                gate.reset()

            if fsm.status in (SOPStatus.STEP_NG, SOPStatus.TIMEOUT):
                # 评测需跑完整段视频，NG/超时不停线，改为继续观察当前步骤
                fsm.status = SOPStatus.RUNNING
            if fsm.status == SOPStatus.COMPLETE:
                break
    finally:
        cap.release()
        if trace:
            trace.close()

    stats = {
        "fps": round(fps, 2),
        "frames_read": frame_index,
        "keyframes": keyframe_count,
        "vlm_calls": len(calls),
        "false_advances": false_advances,
        "completed": fsm.status == SOPStatus.COMPLETE,
        "gate_reasons": dict(gate_reasons),
    }
    return calls, outcomes, stats


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def summarize(
    calls: list[CallRecord], outcomes: list[StepOutcome], stats: dict
) -> dict[str, Any]:
    # 推理失败的返回值和「判否」长得一样，计入指标会把故障粉饰成正确的否定判定
    failed = [c for c in calls if c.error]
    calls = [c for c in calls if not c.error]
    counts = Counter(c.outcome for c in calls)
    overall = _prf(counts["TP"], counts["FP"], counts["FN"])
    total = len(calls)
    overall["accuracy"] = (
        round((counts["TP"] + counts["TN"]) / total, 4) if total else 0.0
    )

    per_step: dict[str, Any] = {}
    for step_idx in sorted({c.expected_step for c in calls}):
        subset = [c for c in calls if c.expected_step == step_idx]
        sub_counts = Counter(c.outcome for c in subset)
        per_step[str(step_idx)] = {
            "vlm_calls": len(subset),
            **{k: sub_counts[k] for k in ("TP", "FP", "FN", "TN")},
            **_prf(sub_counts["TP"], sub_counts["FP"], sub_counts["FN"]),
        }

    latencies = [o.latency for o in outcomes if o.latency is not None]
    step_level = {
        "truth_steps": len(outcomes),
        "triggered": sum(1 for o in outcomes if o.triggered_at is not None),
        "missed": [o.step_index for o in outcomes if o.triggered_at is None],
        "false_advances": stats["false_advances"],
        "latency_seconds": {
            "mean": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "max": round(max(latencies), 2) if latencies else None,
            "per_step": {
                str(o.step_index): round(o.latency, 2)
                for o in outcomes
                if o.latency is not None
            },
        },
    }

    infer = [c.infer_ms for c in calls]
    return {
        "decision_level": {
            "confusion": {k: counts[k] for k in ("TP", "FP", "FN", "TN")},
            **overall,
        },
        "per_expected_step": per_step,
        "step_level": step_level,
        "performance": {
            "vlm_calls": len(calls),
            "keyframes": stats["keyframes"],
            "frames_read": stats["frames_read"],
            "avg_infer_ms": round(sum(infer) / len(infer), 1) if infer else None,
            "max_infer_ms": round(max(infer), 1) if infer else None,
            "avg_frames_per_call": round(
                sum(c.frame_count for c in calls) / len(calls), 2
            )
            if calls
            else None,
        },
        "failed_calls": {
            "count": len(failed),
            "samples": [f.error[:120] for f in failed[:3]],
        },
        "gate_reasons": stats["gate_reasons"],
        "reached_complete": stats["completed"],
    }


def print_report(label: str, cfg: EvalConfig, summary: dict) -> None:
    d = summary["decision_level"]
    s = summary["step_level"]
    p = summary["performance"]
    print(f"\n═══ 动作识别评测：{label} ═══")
    print(
        f"配置  窗口={cfg.frame_window}帧×{cfg.frame_interval}s  参考图={'开' if cfg.use_reference else '关'}"
        f"  自适应={'开' if cfg.adaptive_window else '关'}"
        f"  时间宽限={cfg.truth_grace_seconds}s"
        f"  阈值={cfg.min_confidence}  连续通过={cfg.min_consecutive_pass}  温度={cfg.temperature}"
    )
    print(f"模型  YOLO={cfg.yolo_model}  VLM={cfg.vlm_model}")

    print("\n判定级（每次 VLM 调用是否答对「是否在执行期望步骤」）")
    print(
        f"  TP={d['confusion']['TP']}  FP={d['confusion']['FP']}  "
        f"FN={d['confusion']['FN']}  TN={d['confusion']['TN']}"
    )
    print(
        f"  precision={d['precision']}  recall={d['recall']}  f1={d['f1']}  accuracy={d['accuracy']}"
    )

    print("\n各期望步骤")
    print(
        f"  {'步骤':<6}{'调用':>6}{'TP':>5}{'FP':>5}{'FN':>5}{'TN':>5}{'P':>8}{'R':>8}{'F1':>8}"
    )
    for step_idx, m in summary["per_expected_step"].items():
        print(
            f"  {step_idx:<6}{m['vlm_calls']:>6}{m['TP']:>5}{m['FP']:>5}{m['FN']:>5}{m['TN']:>5}"
            f"{m['precision']:>8.3f}{m['recall']:>8.3f}{m['f1']:>8.3f}"
        )

    print("\n步骤级（端到端）")
    print(
        f"  真值步骤 {s['truth_steps']}，成功触发 {s['triggered']}，漏判 {s['missed'] or '无'}"
    )
    print(f"  误推进 {s['false_advances']} 次")
    lat = s["latency_seconds"]
    print(f"  触发延迟 平均 {lat['mean']}s，最大 {lat['max']}s")

    failed = summary["failed_calls"]
    if failed["count"]:
        print(f"\n⚠ {failed['count']} 次 VLM 推理失败，已排除在指标外")
        for sample in failed["samples"]:
            print(f"    {sample}")

    print("\n性能")
    print(
        f"  VLM 调用 {p['vlm_calls']} 次（关键帧 {p['keyframes']} / 总帧 {p['frames_read']}）"
    )
    print(
        f"  平均 {p['avg_infer_ms']}ms，峰值 {p['max_infer_ms']}ms，每次 {p['avg_frames_per_call']} 帧"
    )
    print(f"  跑完整段并 COMPLETE: {'是' if summary['reached_complete'] else '否'}")

    reasons = summary["gate_reasons"]
    if reasons:
        detail = "  ".join(
            f"{k}={v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])
        )
        print(f"\n门控放行原因分布（判定被跳过的原因在此定位）\n  {detail}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="动作识别准度离线评测")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument(
        "--timeline",
        type=Path,
        required=True,
        help="标注 CSV（annotate_timeline.py 生成）",
    )
    parser.add_argument("--template", type=Path, required=True, help="SOP 模板 JSON")
    parser.add_argument("--label", default="run", help="本次配置的名字，用于对比")
    parser.add_argument("--out-dir", type=Path, default=Path("eval/results"))
    parser.add_argument(
        "--frame-window", type=int, default=4, help="时序窗口帧数，1 表示单帧"
    )
    parser.add_argument(
        "--frame-interval", type=float, default=0.4, help="时序窗口抽帧间隔（秒）"
    )
    parser.add_argument(
        "--no-reference", action="store_true", help="不向 VLM 提供步骤参考图"
    )
    parser.add_argument(
        "--min-confidence", type=float, default=SOPStateMachine.MIN_CONFIDENCE
    )
    parser.add_argument("--min-pass", type=int, default=3, help="连续通过帧数要求")
    parser.add_argument("--ng-tolerance", type=int, default=5)
    parser.add_argument(
        "--stride", type=int, default=1, help="每 N 帧处理一帧，加速回放"
    )
    parser.add_argument(
        "--idle-max", type=float, default=5.0, help="静止画面下强制判定的间隔（秒）"
    )
    parser.add_argument(
        "--gate-cooldown",
        type=float,
        default=None,
        help="覆盖 VLM 门控冷却（秒）。调小可提高采样密度，代价是偏离产线节流",
    )
    parser.add_argument(
        "--no-adaptive-window",
        action="store_true",
        help="关闭按步骤类型分流，所有步骤都走完整时序窗口",
    )
    parser.add_argument(
        "--truth-grace",
        type=float,
        default=1.0,
        help="真值时间窗宽限（秒）。动作对错不以精确秒数卡控，早/晚在此范围内不算误报",
    )
    parser.add_argument("--yolo-model", default="yolo11n.pt")
    parser.add_argument("--vlm-model", default="qwen3-vl:8b-instruct")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="评测默认 0 以保证可复现；产线默认 0.1",
    )
    parser.add_argument("--global-detect", action="store_true", help="按乱序模式评测")
    parser.add_argument(
        "--mock-vlm",
        action="store_true",
        help="用真值假 VLM 自检评测脚本，不需要 Ollama",
    )
    args = parser.parse_args()

    intervals = load_timeline(args.timeline)
    template = json.loads(args.template.read_text(encoding="utf-8"))
    cfg = EvalConfig(
        frame_window=args.frame_window,
        frame_interval=args.frame_interval,
        use_reference=not args.no_reference,
        min_confidence=args.min_confidence,
        min_consecutive_pass=args.min_pass,
        ng_tolerance=args.ng_tolerance,
        yolo_model=resolve_yolo_model(args.yolo_model),
        vlm_model="mock" if args.mock_vlm else args.vlm_model,
        stride=max(1, args.stride),
        idle_max_seconds=args.idle_max,
        temperature=args.temperature,
        gate_cooldown=args.gate_cooldown,
        adaptive_window=not args.no_adaptive_window,
        truth_grace_seconds=max(0.0, args.truth_grace),
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = args.out_dir / f"{args.label}_trace.jsonl"

    vlm: Any = (
        MockVLM(intervals)
        if args.mock_vlm
        else VLMClient(
            base_url=args.ollama_url,
            model=args.vlm_model,
            use_reference_frame=cfg.use_reference,
            temperature=args.temperature,
        )
    )
    try:
        calls, outcomes, stats = replay(
            args.video,
            intervals,
            template,
            cfg,
            vlm=vlm,
            global_detect=args.global_detect,
            trace_path=trace_path,
        )
    finally:
        vlm.close()

    if not calls:
        raise SystemExit(
            "整段视频没有触发任何 VLM 判定，请检查运动检测阈值与 VLM 门控配置"
        )

    summary = summarize(calls, outcomes, stats)
    summary["label"] = args.label
    summary["config"] = cfg.__dict__

    result_path = args.out_dir / f"{args.label}_summary.json"
    result_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print_report(args.label, cfg, summary)
    print(f"明细: {trace_path}\n汇总: {result_path}")


if __name__ == "__main__":
    main()
