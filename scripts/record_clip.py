"""摄像头录制工具 — 采集作业动作片段，供标注与离线评测使用。

输出与 data/clips 下既有片段一致（mp4v 编码），可直接交给
scripts/annotate_timeline.py 标注、scripts/eval_action_recognition.py 评测。

时间轴严格对齐：按目标 fps 节流写帧，相机掉帧时补上一帧，
保证「第 N 秒」在文件里就是第 N 秒——评测的真值区间依赖这一点。

用法：
    python scripts/record_clip.py                      # 默认录 15 秒
    python scripts/record_clip.py --seconds 30 --name SCREW
    python scripts/record_clip.py --device 1 --no-preview
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2

DEFAULT_OUT_DIR = Path("data/clips")
WARMUP_SECONDS = 5.0
WARMUP_FRAMES = 15


def _open_camera(device: int, width: int, height: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(device)
    if not cap.isOpened():
        raise SystemExit(f"无法打开摄像头设备 {device}，请检查设备号与系统相机权限")
    if width and height:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    # 相机开机与切分辨率后出图不稳，且前几帧曝光未收敛。
    # 要求连续读到若干帧才算就绪，避免片头是一段近乎静止的画面。
    deadline = time.monotonic() + WARMUP_SECONDS
    streak = 0
    while time.monotonic() < deadline:
        if cap.read()[0]:
            streak += 1
            if streak >= WARMUP_FRAMES:
                return cap
        else:
            streak = 0
            time.sleep(0.05)
    cap.release()
    raise SystemExit(f"摄像头设备 {device} 打开成功但读不到画面，换一个 --device 试试")


def _draw_hud(frame, elapsed: float, total: float, recording: bool):
    """在预览画面上叠加状态，录制内容本身不带 HUD。"""
    canvas = frame.copy()
    if recording:
        text = f"REC {elapsed:5.1f}s / {total:.0f}s"
        color = (0, 0, 255)
        cv2.circle(canvas, (34, 34), 12, color, -1)
    else:
        text = f"{elapsed:.0f}"
        color = (0, 255, 255)
    cv2.putText(
        canvas, text, (60, 46), cv2.FONT_HERSHEY_SIMPLEX, 1.1, color, 2, cv2.LINE_AA
    )
    cv2.putText(
        canvas,
        "press q to stop",
        (60, 82),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (200, 200, 200),
        1,
        cv2.LINE_AA,
    )
    return canvas


def _countdown(cap: cv2.VideoCapture, seconds: int, preview: bool) -> None:
    if seconds <= 0:
        return
    start = time.monotonic()
    while True:
        remain = seconds - (time.monotonic() - start)
        if remain <= 0:
            break
        ok, frame = cap.read()
        if not ok:
            continue
        if preview:
            cv2.imshow("SOP 录制", _draw_hud(frame, remain, seconds, recording=False))
            if cv2.waitKey(1) & 0xFF == ord("q"):
                raise SystemExit("已取消录制")
        print(f"\r开始前倒计时 {remain:.0f}s ...", end="", flush=True)
    print("\r" + " " * 32 + "\r", end="", flush=True)


def record(
    device: int,
    seconds: float,
    fps: int,
    out_path: Path,
    *,
    width: int,
    height: int,
    preview: bool,
    countdown: int,
) -> Path:
    cap = _open_camera(device, width, height)
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(
        f"摄像头 {device} 已就绪：{actual_w}x{actual_h}，按 {fps}fps 录制 {seconds:.0f} 秒"
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (actual_w, actual_h)
    )
    if not writer.isOpened():
        cap.release()
        raise SystemExit(f"无法创建视频文件: {out_path}")

    try:
        _countdown(cap, countdown, preview)

        total_frames = int(round(seconds * fps))
        start = time.monotonic()
        last_frame = None
        written = 0
        dropped = 0

        for index in range(total_frames):
            # 按目标节拍推进，相机快了就等、慢了就补帧，保证输出时长准确
            target_at = start + index / fps
            while True:
                ok, frame = cap.read()
                if ok:
                    last_frame = frame
                    break
                if last_frame is not None:
                    frame = last_frame
                    dropped += 1
                    break
                time.sleep(0.005)

            writer.write(frame)
            written += 1
            elapsed = time.monotonic() - start

            if preview:
                cv2.imshow(
                    "SOP 录制", _draw_hud(frame, elapsed, seconds, recording=True)
                )
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("\n已手动停止")
                    break

            print(f"\r录制中 {elapsed:5.1f}s / {seconds:.0f}s", end="", flush=True)
            sleep_for = target_at + 1 / fps - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)

        duration = written / fps
        print(
            f"\n完成：{written} 帧，时长 {duration:.2f}s"
            + (f"，补帧 {dropped}" if dropped else "")
        )
    finally:
        writer.release()
        cap.release()
        if preview:
            cv2.destroyAllWindows()

    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="摄像头录制作业动作片段")
    parser.add_argument("--device", type=int, default=0, help="摄像头设备号（0=内置）")
    parser.add_argument("--seconds", type=float, default=15.0, help="录制时长（秒）")
    parser.add_argument(
        "--fps", type=int, default=25, help="录制帧率，需与相机能力匹配"
    )
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--name", default="REC", help="输出文件名前缀，建议写工序名")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--countdown", type=int, default=3, help="开录前的准备倒计时（秒）"
    )
    parser.add_argument("--no-preview", action="store_true", help="不弹预览窗口")
    args = parser.parse_args()

    out_path = args.out_dir / f"{args.name}_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
    saved = record(
        args.device,
        args.seconds,
        args.fps,
        out_path,
        width=args.width,
        height=args.height,
        preview=not args.no_preview,
        countdown=args.countdown,
    )

    print(f"\n已保存: {saved}")
    print("下一步，生成标注缩略图：")
    print(
        f"  python scripts/annotate_timeline.py {saved} --interval 0.5 --out-dir eval/annotations"
    )


if __name__ == "__main__":
    main()
