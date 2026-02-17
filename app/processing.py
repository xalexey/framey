import sys
import os
import cv2
import numpy as np
import cvzone
from ultralytics import YOLO
from math import sqrt

# Ensure project root is on path so sort.py can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sort import Sort

def check_object(x: int, y: int, settings: dict):
    a = settings.get("a")
    b = settings.get("b")
    offset = settings.get("offset")
    length = abs(a*x - y + b) / sqrt(a*a + 1)
    if length <= offset:
        return True
    else:
        return False

def process_video(video_path: str, output_path: str, settings: dict) -> int:
    """Process a video file and return the number of cars counted."""
    #line_y = settings.get("line_y", 400)
    #offset = settings.get("offset", 6)
    confidence = settings.get("confidence", 0.5)
    car_class_id = settings.get("car_class_id", 2)

    model_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "yolov8n.pt")
    model = YOLO(model_path)

    tracker = Sort(max_age=20, min_hits=3, iou_threshold=0.3)

    cap = cv2.VideoCapture(video_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30

    out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    counted_ids: set[int] = set()

    while True:
        success, frame = cap.read()
        if not success:
            break

        results = model(frame, verbose=False)

        detections = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                cls = int(box.cls[0])

                if cls == car_class_id and conf > confidence:
                    detections.append([x1, y1, x2, y2, conf])

        if len(detections) == 0:
            tracked_objects = []
        else:
            tracked_objects = tracker.update(np.array(detections))

        cv2.line(frame, (0, line_y), (w, line_y), (0, 255, 0), 2)

        for track in tracked_objects:
            x1, y1, x2, y2, track_id = map(int, track)
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

            cvzone.cornerRect(frame, (x1, y1, x2 - x1, y2 - y1), l=8, rt=2, colorR=(255, 0, 0))
            cv2.circle(frame, (cx, cy), 4, (0, 0, 255), -1)
            cv2.putText(frame, f"{track_id}", (x1, y1 - 10), cv2.FONT_HERSHEY_PLAIN, 1, (255, 0, 0), 2)

            #if (line_y - offset) < cy < (line_y + offset):
            if check_object(cx, cy, settings):
                if track_id not in counted_ids:
                    counted_ids.add(track_id)

        cv2.putText(frame, f"Cars Counted: {len(counted_ids)}", (10, 50),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 0), 3)

        out.write(frame)

    cap.release()
    out.release()

    return len(counted_ids)
