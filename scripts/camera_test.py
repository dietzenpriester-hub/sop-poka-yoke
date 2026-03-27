"""简化版摄像头实时检测脚本 — 用于快速验证 YOLO + MQTT 推送

使用方法:
    1. 手机安装 IP 摄像头 App（推荐 IP摄像头/DroidCam/iVCam）
    2. 确保手机和电脑在同一 WiFi
    3. 获取手机 App 提供的视频流 URL（通常是 http://手机IP:端口/video）
    4. 运行: python scripts/camera_test.py --url http://192.168.x.x:8080/video
       或使用电脑摄像头: python scripts/camera_test.py --url 0
"""
import argparse
import json
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "server"))

import cv2
import numpy as np
from ultralytics import YOLO

try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False


def main():
    parser = argparse.ArgumentParser(description="摄像头实时检测测试")
    parser.add_argument("--url", default="0", help="摄像头 URL 或设备编号（0=电脑摄像头）")
    parser.add_argument("--model", default="yolo11n.pt", help="YOLO 模型文件")
    parser.add_argument("--station", default="station-test", help="工位 ID")
    parser.add_argument("--mqtt-host", default="localhost", help="MQTT Broker 地址")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT 端口")
    parser.add_argument("--interval", type=float, default=2.0, help="检测间隔（秒）")
    parser.add_argument("--conf", type=float, default=0.4, help="YOLO 置信度阈值")
    parser.add_argument("--show", action="store_true", help="显示视频画面（需要 GUI）")
    args = parser.parse_args()

    source = int(args.url) if args.url.isdigit() else args.url
    print(f"\n{'='*50}")
    print(f"  SOP 防呆 — 摄像头实时检测测试")
    print(f"{'='*50}")
    print(f"  摄像头: {source}")
    print(f"  模型:   {args.model}")
    print(f"  工位:   {args.station}")
    print(f"  间隔:   {args.interval}s")
    print(f"{'='*50}\n")

    print("加载 YOLO 模型...")
    model = YOLO(args.model)
    try:
        import torch
        if torch.backends.mps.is_available():
            model.to("mps")
            print("  使用 Apple Silicon MPS 加速")
    except Exception:
        pass

    mqtt_client = None
    if HAS_MQTT:
        try:
            mqtt_client = mqtt.Client()
            mqtt_client.connect(args.mqtt_host, args.mqtt_port, 60)
            mqtt_client.loop_start()
            print(f"  MQTT 已连接: {args.mqtt_host}:{args.mqtt_port}")
        except Exception as e:
            print(f"  MQTT 连接失败: {e}（将只在终端显示结果）")
            mqtt_client = None
    else:
        print("  paho-mqtt 未安装，将只在终端显示结果")

    print(f"\n正在连接摄像头 {source} ...")
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"  无法打开摄像头: {source}")
        print("  请检查 URL 是否正确，或手机 App 是否已启动")
        return

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"  摄像头已连接: {w}x{h} @ {fps:.0f}fps")
    print(f"\n开始实时检测（按 Ctrl+C 停止）...\n")

    frame_count = 0
    detect_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("  帧读取失败，尝试重连...")
                time.sleep(1)
                cap.release()
                cap = cv2.VideoCapture(source)
                continue

            frame_count += 1
            if frame_count % max(1, int(fps * args.interval)) != 0:
                if args.show:
                    cv2.imshow("SOP Camera Test", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                continue

            detect_count += 1
            results = model.predict(frame, conf=args.conf, verbose=False)

            detections = []
            if results and results[0].boxes is not None:
                boxes = results[0].boxes
                for i in range(len(boxes)):
                    cls_id = int(boxes.cls[i].item())
                    cls_name = results[0].names.get(cls_id, f"class_{cls_id}")
                    conf_val = float(boxes.conf[i].item())
                    detections.append({
                        "class": cls_name,
                        "confidence": round(conf_val, 3),
                    })

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            payload = {
                "station_id": args.station,
                "timestamp": timestamp,
                "frame_index": frame_count,
                "detections": detections,
                "object_count": len(detections),
                "unique_classes": list(set(d["class"] for d in detections)),
            }

            class_summary = ", ".join(f"{c}x{sum(1 for d in detections if d['class']==c)}"
                                       for c in set(d["class"] for d in detections))
            print(f"[{timestamp}] 检测 #{detect_count}: "
                  f"{len(detections)} 个物体 ({class_summary or '无'})")

            if mqtt_client:
                topic = f"sop/{args.station}/detection"
                mqtt_client.publish(topic, json.dumps(payload, ensure_ascii=False))

            if args.show and results:
                annotated = results[0].plot()
                cv2.imshow("SOP Camera Test", annotated)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except KeyboardInterrupt:
        print(f"\n\n检测结束。共处理 {frame_count} 帧，执行 {detect_count} 次检测。")
    finally:
        cap.release()
        if args.show:
            cv2.destroyAllWindows()
        if mqtt_client:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()


if __name__ == "__main__":
    main()
