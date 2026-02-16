import os
import uuid

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.auth import get_current_user
from app.database import (
    create_tables,
    get_user_settings,
    update_user_settings,
    create_task,
    update_task_status,
    get_task,
    get_tasks_for_user,
)
from app.processing import process_video

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")

app = FastAPI(title="VisiTrack API", version="1.0.0")

ALLOWED_EXTENSIONS = {"mp4", "avi", "mov"}


@app.on_event("startup")
def startup():
    create_tables()
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)


class SettingsUpdate(BaseModel):
    line_y: int = 400
    offset: int = 6
    confidence: float = 0.5
    car_class_id: int = 2


def _run_processing(task_id: str, video_path: str, output_path: str, settings: dict):
    try:
        update_task_status(task_id, "processing")
        car_count = process_video(video_path, output_path, settings)
        update_task_status(task_id, "done", car_count=car_count)
    except Exception as e:
        update_task_status(task_id, "error", error_message=str(e))


@app.post("/api/upload")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file format. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    task_id = str(uuid.uuid4())
    saved_filename = f"{task_id}.{ext}"
    video_path = os.path.join(UPLOAD_DIR, saved_filename)
    output_path = os.path.join(OUTPUT_DIR, saved_filename)

    content = await file.read()
    with open(video_path, "wb") as f:
        f.write(content)

    create_task(task_id, user["id"], file.filename)

    settings = get_user_settings(user["id"])
    background_tasks.add_task(_run_processing, task_id, video_path, output_path, settings)

    return {"task_id": task_id, "message": "Файл принят на обработку"}


@app.get("/api/tasks/{task_id}")
def get_task_status(task_id: str, user: dict = Depends(get_current_user)):
    task = get_task(task_id, user["id"])
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": task["id"],
        "status": task["status"],
        "car_count": task["car_count"],
        "filename": task["filename"],
        "created_at": task["created_at"],
        "finished_at": task["finished_at"],
    }


@app.get("/api/tasks")
def list_tasks(user: dict = Depends(get_current_user)):
    tasks = get_tasks_for_user(user["id"])
    return [
        {
            "task_id": t["id"],
            "status": t["status"],
            "car_count": t["car_count"],
            "filename": t["filename"],
            "created_at": t["created_at"],
            "finished_at": t["finished_at"],
        }
        for t in tasks
    ]


@app.get("/api/settings")
def read_settings(user: dict = Depends(get_current_user)):
    settings = get_user_settings(user["id"])
    return {
        "line_y": settings["line_y"],
        "offset": settings["offset"],
        "confidence": settings["confidence"],
        "car_class_id": settings["car_class_id"],
    }


@app.put("/api/settings")
def update_settings(body: SettingsUpdate, user: dict = Depends(get_current_user)):
    update_user_settings(user["id"], body.model_dump())
    return {"message": "Settings updated"}
