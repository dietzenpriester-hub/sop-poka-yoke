"""YOLO 检测器单元测试（Mock）"""

from src.inference.yolo_detector import ObjectTracker, Detection


def test_object_tracker_place_and_remove():
    tracker = ObjectTracker(stable_threshold=2)
    det = Detection(class_id=0, class_name="screwdriver", confidence=0.9, bbox=(0, 0, 100, 100), center=(50, 50))
    tracker.update([det])
    events = tracker.update([det])
    assert any(e["type"] == "object_placed" for e in events)

    events = tracker.update([])
    events = tracker.update([])
    assert any(e["type"] == "object_removed" for e in events)
