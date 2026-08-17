"""动作识别评测标注辅助工具。

从视频按固定间隔抽帧，导出带时间戳的缩略图contact sheet 和一份待填的标注 CSV，
人工对照缩略图填写每个步骤的起止秒数即可。

标注 CSV 格式（供 eval_action_recognition.py 消费）：

    video,start_sec,end_sec,step_index,step_name,note
    test-manufacturing.mp4,0.0,3.5,-1,idle,开机等待
    test-manufacturing.mp4,3.5,8.2,0,安装底座,
    test-manufacturing.mp4,8.2,12.0,1,固定骨架,

- step_index：SOP 模板中的步骤下标（从 0 开始）；-1 表示空闲/无相关操作
- 区间为左闭右开，未被任何区间覆盖的时间默认视为 idle（step_index=-1）
- 允许同一步骤拆成多段（例如中间被打断）

用法：
    python scripts/annotate_timeline.py data/clips/xxx.mp4 --interval 1.0
    python scripts/annotate_timeline.py <video> --out-dir eval/annotations
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import cv2

CONTACT_SHEET_COLS = 6
THUMB_WIDTH = 320
LABEL_HEIGHT = 28
LABEL_COLOR = (255, 255, 255)
LABEL_BG = (0, 0, 0)


def _grab_frames(video_path: Path, interval: float) -> tuple[list[tuple[float, "cv2.Mat"]], float]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise SystemExit(f"无法打开视频: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total / fps if total else 0.0

    step = max(1, int(round(fps * interval)))
    frames: list[tuple[float, cv2.Mat]] = []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            frames.append((idx / fps, frame))
        idx += 1
    cap.release()
    if not duration:
        duration = idx / fps if idx else 0.0
    return frames, duration


def _build_contact_sheet(frames: list[tuple[float, "cv2.Mat"]]) -> "cv2.Mat":
    thumbs = []
    for ts, frame in frames:
        h, w = frame.shape[:2]
        thumb = cv2.resize(frame, (THUMB_WIDTH, int(h * THUMB_WIDTH / w)), interpolation=cv2.INTER_AREA)
        bar = cv2.copyMakeBorder(
            thumb, 0, LABEL_HEIGHT, 0, 0, cv2.BORDER_CONSTANT, value=LABEL_BG
        )
        cv2.putText(
            bar, f"{ts:7.2f}s", (6, thumb.shape[0] + 20),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, LABEL_COLOR, 1, cv2.LINE_AA,
        )
        thumbs.append(bar)

    cols = min(CONTACT_SHEET_COLS, len(thumbs))
    rows = math.ceil(len(thumbs) / cols)
    cell_h, cell_w = thumbs[0].shape[:2]
    blank = thumbs[0].copy()
    blank[:] = LABEL_BG
    thumbs.extend(blank for _ in range(rows * cols - len(thumbs)))
    return cv2.vconcat([cv2.hconcat(thumbs[r * cols:(r + 1) * cols]) for r in range(rows)])


def _write_template_csv(csv_path: Path, video_name: str, duration: float) -> None:
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["video", "start_sec", "end_sec", "step_index", "step_name", "note"])
        writer.writerow([video_name, "0.0", f"{duration:.2f}", "-1", "idle", "请按缩略图拆分并填写各步骤区间"])


def main() -> None:
    parser = argparse.ArgumentParser(description="导出缩略图与标注 CSV 模板")
    parser.add_argument("video", type=Path, help="视频文件路径")
    parser.add_argument("--interval", type=float, default=1.0, help="抽帧间隔（秒），默认 1.0")
    parser.add_argument("--out-dir", type=Path, default=Path("eval/annotations"), help="输出目录")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    frames, duration = _grab_frames(args.video, args.interval)
    if not frames:
        raise SystemExit(f"未从视频中读到任何帧: {args.video}")

    stem = args.video.stem
    sheet_path = args.out_dir / f"{stem}_contact_sheet.jpg"
    cv2.imwrite(str(sheet_path), _build_contact_sheet(frames), [cv2.IMWRITE_JPEG_QUALITY, 85])

    csv_path = args.out_dir / f"{stem}_timeline.csv"
    if csv_path.exists():
        print(f"标注 CSV 已存在，保留不覆盖: {csv_path}")
    else:
        _write_template_csv(csv_path, args.video.name, duration)
        print(f"标注 CSV 模板已生成: {csv_path}")

    print(f"视频时长 {duration:.2f}s，抽取 {len(frames)} 帧")
    print(f"缩略图: {sheet_path}")
    print("对照缩略图填好 CSV 后，运行 scripts/eval_action_recognition.py 评测")


if __name__ == "__main__":
    main()
