"""YOLO 推理性能基准测试"""

import time

import numpy as np
from ultralytics import YOLO


def main(frames: int = 1000):
    model = YOLO("yolo11n.pt")
    dummy = np.zeros((640, 640, 3), dtype=np.uint8)
    t0 = time.perf_counter()
    for _ in range(frames):
        model(dummy, verbose=False)
    dt = time.perf_counter() - t0
    print(f"总耗时 {dt:.3f}s, 平均每帧 {dt / frames * 1000:.2f} ms")


if __name__ == "__main__":
    main()
