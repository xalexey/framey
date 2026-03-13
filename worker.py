"""
VisiTrack Worker — runs on a local PC with GPU.
Polls the server for pending tasks, downloads videos,
processes them locally, and uploads results back.

Usage:
    python worker.py --server http://89.124.66.107:8000 --api-key YOUR_API_KEY

Requires sort.py and yolov8n.pt in the same directory.

Requires packages
numpy
opencv-python
cvzone
requests
ultralytics
scikit-image
filterpy
"""

import argparse
import os
import sys
import time
import tempfile
import shutil
from math import sqrt

from datetime import datetime, UTC

import cv2
import numpy as np
import cvzone
import requests
from ultralytics import YOLO

from sort import Sort


def check_object(x: int, y: int, settings: dict) -> bool:
    a = settings.get("a")
    b = settings.get("b")
    offset = settings.get("offset")
    length = abs(a * x - y + b) / sqrt(a * a + 1)
    return length <= offset


def process_video(video_path: str, output_path: str, settings: dict,
                  server_url: str = None, api_key: str = None, task_id: str = None) -> int:
    a = settings.get("a")
    b = settings.get("b")
    confidence = settings.get("confidence", 0.5)
    car_class_id = settings.get("car_class_id", 2)

    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yolov8n.pt")
    model = YOLO(model_path)

    tracker = Sort(max_age=20, min_hits=3, iou_threshold=0.3)

    cap = cv2.VideoCapture(video_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    counted_ids: set[int] = set()
    frame_num = 0
    tracked_objects = []
    last_reported_progress = 0

    while True:
        success, frame = cap.read()
        if not success:
            break

        if frame_num % 2 == 0:
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

        cv2.line(frame, (0, int(b)), (w, int(a * w + b)), (0, 255, 0), 2)

        for track in tracked_objects:
            x1, y1, x2, y2, track_id = map(int, track)
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

            cvzone.cornerRect(frame, (x1, y1, x2 - x1, y2 - y1), l=8, rt=2, colorR=(255, 0, 0))
            cv2.circle(frame, (cx, cy), 4, (0, 0, 255), -1)
            cv2.putText(frame, f"{track_id}", (x1, y1 - 10), cv2.FONT_HERSHEY_PLAIN, 1, (255, 0, 0), 2)

            if check_object(cx, cy, settings):
                if track_id not in counted_ids:
                    counted_ids.add(track_id)

        cv2.putText(frame, f"Cars Counted: {len(counted_ids)}", (10, 50),
                    cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 0), 3)

        out.write(frame)
        frame_num += 1

        if task_id and total_frames > 0:
            progress = int(frame_num / total_frames * 100)
            if progress >= last_reported_progress + 5:
                last_reported_progress = progress // 5 * 5
                report_progress(server_url, api_key, task_id, last_reported_progress)

    cap.release()
    out.release()

    return len(counted_ids)


def report_progress(server_url: str, api_key: str, task_id: str, progress: int):
    try:
        requests.post(
            f"{server_url}/api/worker/tasks/{task_id}/progress",
            params={"progress": progress},
            headers={"X-Api-Key": api_key},
            timeout=10,
        )
    except Exception:
        pass


def poll_task(server_url: str, api_key: str) -> dict | None:
    resp = requests.get(
        f"{server_url}/api/worker/tasks",
        headers={"X-Api-Key": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data is None:
        return None
    return data


def download_file(server_url: str, api_key: str, file_id: str, dest_path: str):
    resp = requests.get(
        f"{server_url}/api/worker/files/{file_id}",
        headers={"X-Api-Key": api_key},
        stream=True,
        timeout=300,
    )
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def upload_result(server_url: str, api_key: str, task_id: str, output_path: str, car_count: int):
    with open(output_path, "rb") as f:
        resp = requests.post(
            f"{server_url}/api/worker/tasks/{task_id}/result",
            params={"car_count": car_count},
            headers={"X-Api-Key": api_key},
            files={"file": (os.path.basename(output_path), f, "video/mp4")},
            timeout=600,
        )
    resp.raise_for_status()


def report_error(server_url: str, api_key: str, task_id: str, error_msg: str):
    try:
        requests.post(
            f"{server_url}/api/worker/tasks/{task_id}/result",
            params={"car_count": 0, "error": error_msg},
            headers={"X-Api-Key": api_key},
            files={"file": ("empty.mp4", b"", "video/mp4")},
            timeout=10,
        )
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="VisiTrack Worker")
    parser.add_argument("--server", required=True, help="Server URL, e.g. http://89.124.66.107:8000")
    parser.add_argument("--api-key", required=True, help="API key for authentication")
    parser.add_argument("--interval", type=int, default=5, help="Poll interval in seconds (default: 5)")
    args = parser.parse_args()

    server_url = args.server.rstrip("/")
    api_key = args.api_key
    poll_interval = args.interval

    work_dir = os.path.join(tempfile.gettempdir(), "visitrack_worker")
    os.makedirs(work_dir, exist_ok=True)

    print(f"VisiTrack Worker started")
    print(f"Server: {server_url}")
    print(f"Poll interval: {poll_interval}s")
    print(f"Work directory: {work_dir}")
    print()

    while True:
        try:
            task = poll_task(server_url, api_key)
        except Exception as e:
            print(f"Error polling server: {e}")
            time.sleep(poll_interval)
            continue

        if task is None:
            time.sleep(poll_interval)
            continue

        task_id = task["task_id"]
        file_id = task["file_id"]
        filename = task["filename"]
        settings = task["settings"]

        print(f"Got task {task_id} (file: {filename})")

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp4"
        input_path = os.path.join(work_dir, f"{file_id}.{ext}")
        output_path = os.path.join(work_dir, f"{file_id}_output.{ext}")

        try:
            print(f"  Downloading {filename}...")
            download_file(server_url, api_key, file_id, input_path)

            print(f"  Processing... - {datetime.now(UTC)}")
            report_progress(server_url, api_key, task_id, -1)
            car_count = process_video(
                input_path, output_path, settings,
                server_url=server_url, api_key=api_key, task_id=task_id,
            )

            print(f"  Uploading result (cars counted: {car_count})...")
            upload_result(server_url, api_key, task_id, output_path, car_count)
            print(f"  Done! - {datetime.now(UTC)}")

        except Exception as e:
            print(f"  Error: {e}")
            report_error(server_url, api_key, task_id, str(e))

        finally:
            for path in (input_path, output_path):
                if os.path.exists(path):
                    os.remove(path)

        print()


if __name__ == "__main__":
    main()
