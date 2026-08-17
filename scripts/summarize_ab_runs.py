"""汇总多次 A/B 评测结果，给出均值与波动范围。

单次运行的样本量很小，VLM 采样噪声足以让 F1 摆动几十个百分点。此脚本把同一
配置的多次重复聚合起来，只有当差异大于重复间波动时，配置改动才算真的有效。

用法：
    python scripts/summarize_ab_runs.py                    # 汇总 eval/results 下全部
    python scripts/summarize_ab_runs.py --scene pickup     # 只看某个场景
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

RESULT_GLOB = "*_summary.json"
# 批量实验的 label 形如 pickup_w4_r2（全多帧）或 pickup_w4a_r2（自适应）
LABEL_PATTERN = re.compile(
    r"^(?P<scene>[a-z0-9\-]+)_w(?P<window>\d+)(?P<adapt>a)?_r(?P<rep>\d+)$"
)

METRICS = [
    ("precision", "精确率"),
    ("recall", "召回率"),
    ("f1", "F1"),
    ("accuracy", "准确率"),
]


GroupKey = tuple[str, int, str]


def collect(
    results_dir: Path, scene_filter: str | None
) -> dict[GroupKey, list[dict[str, Any]]]:
    grouped: dict[GroupKey, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(results_dir.glob(RESULT_GLOB)):
        data = json.loads(path.read_text(encoding="utf-8"))
        match = LABEL_PATTERN.match(str(data.get("label", "")))
        if not match:
            continue
        scene = match.group("scene")
        if scene_filter and scene != scene_filter:
            continue
        adapt = match.group("adapt") or ""
        grouped[(scene, int(match.group("window")), adapt)].append(data)
    return grouped


def _mode_label(window: int, adapt: str) -> str:
    if window == 1:
        return "单帧"
    if adapt == "a":
        return f"{window} 帧自适应（place 走单帧）"
    return f"{window} 帧时序"


def _spread(values: list[float]) -> str:
    """用均值与极差描述波动；重复次数少时标准差意义有限，极差更直观。"""
    if not values:
        return "—"
    mean = statistics.mean(values)
    if len(values) == 1:
        return f"{mean:.2f}"
    return f"{mean:.2f} [{min(values):.2f}~{max(values):.2f}]"


def report(grouped: dict[GroupKey, list[dict[str, Any]]]) -> None:
    if not grouped:
        print("未找到批量实验结果，请先运行 scripts/run_ab_batch.sh")
        return

    for scene in sorted({s for s, _, _ in grouped}):
        print(f"\n═══ 场景：{scene} ═══")
        keys = sorted(
            (k for k in grouped if k[0] == scene),
            key=lambda k: (k[1], k[2]),
        )
        for key in keys:
            _scene, window, adapt = key
            runs = grouped[key]
            decisions = [r["decision_level"] for r in runs]
            print(f"\n  {_mode_label(window, adapt)}（{len(runs)} 次重复）")
            for metric_key, name in METRICS:
                print(f"    {name:<6} {_spread([d[metric_key] for d in decisions])}")

            conf = [d["confusion"] for d in decisions]
            for tag in ("TP", "FP", "FN", "TN"):
                total = sum(c[tag] for c in conf)
                print(
                    f"    {tag:<6} 合计 {total:>3}  每次 {_spread([float(c[tag]) for c in conf])}"
                )

            advances = [float(r["step_level"]["false_advances"]) for r in runs]
            triggered = [float(r["step_level"]["triggered"]) for r in runs]
            truth_steps = runs[0]["step_level"]["truth_steps"]
            latency = [
                r["step_level"]["latency_seconds"]["mean"]
                for r in runs
                if r["step_level"]["latency_seconds"]["mean"] is not None
            ]
            infer = [
                r["performance"]["avg_infer_ms"]
                for r in runs
                if r["performance"]["avg_infer_ms"]
            ]
            calls = [float(r["performance"]["vlm_calls"]) for r in runs]
            failed = sum(r.get("failed_calls", {}).get("count", 0) for r in runs)

            print(f"    误放行  合计 {int(sum(advances)):>3}  每次 {_spread(advances)}")
            print(f"    触发步骤 {_spread(triggered)} / {truth_steps}")
            print(
                f"    触发延迟 {_spread(latency)} s"
                if latency
                else "    触发延迟 —（无步骤被触发）"
            )
            print(f"    判定次数 {_spread(calls)}   推理耗时 {_spread(infer)} ms")
            if failed:
                print(f"    ⚠ 推理失败 {failed} 次（已排除）")

    print("\n提示：只有当两组的区间不重叠时，差异才明显超出采样噪声。\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="汇总 A/B 批量评测结果")
    parser.add_argument("--results-dir", type=Path, default=Path("eval/results"))
    parser.add_argument("--scene", default=None, help="只汇总指定场景")
    args = parser.parse_args()
    report(collect(args.results_dir, args.scene))


if __name__ == "__main__":
    main()
