import os
import uuid

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth import get_current_user
from app.database import (
    create_tables,
    create_user,
    get_camera_settings,
    update_camera_settings,
    check_camera_permission,
    grant_camera_permission,
    revoke_camera_permission,
    get_user_cameras,
    get_user_by_id,
    is_admin,
    add_admin,
    remove_admin,
    get_admins,
    create_file,
    get_file,
    update_file_output_path,
    create_task,
    update_task_status,
    update_task_progress,
    get_task,
    get_tasks_for_user,
    get_pending_task,
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


class UserUpdate(BaseModel):
    name: str
    id: int


@app.post("/api/users")
def register_user(body: UserUpdate):
    if body.id == 0:
        user = create_user(body.name)
    else:
        user = get_user_by_id(body.id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": user["id"],
        "name": user["name"],
        "api_key": user["api_key"],
    }


@app.get("/api/users/{user_id}")
def get_user(user_id: int):
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": user["id"],
        "name": user["name"],
        "api_key": user["api_key"],
    }


class SettingsUpdate(BaseModel):
    a: float = 0
    b: float = 400
    offset: int = 6
    confidence: float = 0.5
    car_class_id: int = 2
    use_worker: bool = False


class PermissionGrant(BaseModel):
    user_id: int
    camera_code: str


def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    if not is_admin(user["id"]):
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


def _run_processing(task_id: str, video_path: str, output_path: str, settings: dict):
    try:
        update_task_status(task_id, "processing")
        car_count = process_video(video_path, output_path, settings, task_id=task_id)
        update_task_status(task_id, "done", car_count=car_count)
    except Exception as e:
        update_task_status(task_id, "error", error_message=str(e))


@app.post("/api/upload")
async def upload_video(
    camera_code: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file format. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    if not check_camera_permission(user["id"], camera_code):
        raise HTTPException(status_code=403, detail="No permission to upload files for this camera")

    file_id = str(uuid.uuid4())
    saved_filename = f"{file_id}.{ext}"
    video_path = os.path.join(UPLOAD_DIR, saved_filename)

    content = await file.read()
    with open(video_path, "wb") as f:
        f.write(content)

    create_file(file_id, user["id"], camera_code, file.filename, video_path)

    return {"file_id": file_id}


@app.post("/api/process")
def process_file(
    file_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    file_record = get_file(file_id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    if not check_camera_permission(user["id"], file_record["camera_code"]):
        raise HTTPException(status_code=403, detail="No permission to process files for this camera")

    settings = get_camera_settings(file_record["camera_code"])
    if not settings:
        raise HTTPException(status_code=404, detail="Camera settings not found")

    task_id = str(uuid.uuid4())
    ext = file_record["filename"].rsplit(".", 1)[-1].lower() if "." in file_record["filename"] else "mp4"
    output_filename = f"{file_id}.{ext}"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    if os.path.exists(output_path):
        os.remove(output_path)

    update_file_output_path(file_id, output_path)
    create_task(task_id, user["id"], file_record["camera_code"], file_record["filename"], file_id=file_id)

    if settings.get("use_worker"):
        return {"task_id": task_id, "message": "Задача создана, ожидает обработки воркером"}
    else:
        background_tasks.add_task(_run_processing, task_id, file_record["upload_path"], output_path, settings)
        return {"task_id": task_id, "message": "Обработка запущена"}


@app.get("/api/files/output/{file_id}")
def download_output(file_id: str, user: dict = Depends(get_current_user)):
    file_record = get_file(file_id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    if not file_record["output_path"] or not os.path.exists(file_record["output_path"]):
        raise HTTPException(status_code=404, detail="Output file not yet available")

    return FileResponse(file_record["output_path"], filename=file_record["filename"])


@app.get("/api/tasks/{task_id}")
def get_task_status(task_id: str, user: dict = Depends(get_current_user)):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": task["id"],
        "file_id": task["file_id"],
        "camera_code": task["camera_code"],
        "status": task["status"],
        "progress": task["progress"],
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
            "file_id": t["file_id"],
            "camera_code": t["camera_code"],
            "status": t["status"],
            "progress": t["progress"],
            "car_count": t["car_count"],
            "filename": t["filename"],
            "created_at": t["created_at"],
            "finished_at": t["finished_at"],
        }
        for t in tasks
    ]


@app.get("/api/settings")
def read_settings(camera_code: str, user: dict = Depends(get_current_user)):
    if not check_camera_permission(user["id"], camera_code):
        raise HTTPException(status_code=403, detail="No permission for this camera")
    settings = get_camera_settings(camera_code)
    if not settings:
        raise HTTPException(status_code=404, detail="Camera settings not found")
    return {
        "camera_code": camera_code,
        "a": settings["a"],
        "b": settings["b"],
        "offset": settings["offset"],
        "confidence": settings["confidence"],
        "car_class_id": settings["car_class_id"],
        "use_worker": bool(settings["use_worker"]),
    }


@app.put("/api/settings")
def update_settings(camera_code: str, body: SettingsUpdate, user: dict = Depends(get_current_user)):
    if not check_camera_permission(user["id"], camera_code):
        raise HTTPException(status_code=403, detail="No permission for this camera")
    update_camera_settings(camera_code, body.model_dump())
    return {"message": "Settings updated"}


# --- Permission management endpoints (admin only) ---

@app.post("/api/permissions")
def grant_permission(body: PermissionGrant, admin: dict = Depends(get_current_admin)):
    grant_camera_permission(body.user_id, body.camera_code)
    return {"message": "Permission granted"}


@app.delete("/api/permissions")
def revoke_permission(user_id: int, camera_code: str, admin: dict = Depends(get_current_admin)):
    revoke_camera_permission(user_id, camera_code)
    return {"message": "Permission revoked"}


@app.get("/api/permissions")
def list_permissions(user_id: int, user: dict = Depends(get_current_user)):
    cameras = get_user_cameras(user_id)
    return {"user_id": user_id, "cameras": cameras}


# --- Admin management endpoints ---

class AdminGrant(BaseModel):
    user_id: int


@app.get("/api/admins")
def list_admins(admin: dict = Depends(get_current_admin)):
    return get_admins()


@app.post("/api/admins")
def grant_admin(body: AdminGrant, admin: dict = Depends(get_current_admin)):
    add_admin(body.user_id)
    return {"message": "Admin granted"}


@app.delete("/api/admins")
def revoke_admin(user_id: int, admin: dict = Depends(get_current_admin)):
    remove_admin(user_id)
    return {"message": "Admin revoked"}


# --- Worker endpoints ---

@app.get("/api/worker/tasks")
def worker_get_task(user: dict = Depends(get_current_user)):
    task = get_pending_task()
    if not task:
        return None

    settings = get_camera_settings(task["camera_code"])
    return {
        "task_id": task["id"],
        "file_id": task["file_id"],
        "camera_code": task["camera_code"],
        "filename": task["filename"],
        "settings": {
            "a": settings["a"],
            "b": settings["b"],
            "offset": settings["offset"],
            "confidence": settings["confidence"],
            "car_class_id": settings["car_class_id"],
        } if settings else None,
    }


@app.get("/api/worker/files/{file_id}")
def worker_download_file(file_id: str, user: dict = Depends(get_current_user)):
    file_record = get_file(file_id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_record["upload_path"], filename=file_record["filename"])


@app.post("/api/worker/tasks/{task_id}/progress")
def worker_update_progress(task_id: str, progress: int, user: dict = Depends(get_current_user)):
    update_task_status(task_id, "processing")
    update_task_progress(task_id, progress)
    return {"message": "Progress updated"}


@app.post("/api/worker/tasks/{task_id}/result")
async def worker_upload_result(
    task_id: str,
    car_count: int,
    file: UploadFile = File(...),
    error: str | None = None,
    user: dict = Depends(get_current_user),
):
    if error:
        update_task_status(task_id, "error", error_message=error)
        return {"message": "Task marked as error"}

    task_record = get_task(task_id)
    if not task_record:
        raise HTTPException(status_code=404, detail="Task not found")

    file_record = get_file(task_record["file_id"])
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    output_path = file_record["output_path"]
    if not output_path:
        ext = file_record["filename"].rsplit(".", 1)[-1].lower() if "." in file_record["filename"] else "mp4"
        output_path = os.path.join(OUTPUT_DIR, f"{file_record['id']}.{ext}")
        update_file_output_path(file_record["id"], output_path)

    content = await file.read()
    with open(output_path, "wb") as f:
        f.write(content)

    update_task_progress(task_id, 100)
    update_task_status(task_id, "done", car_count=car_count)
    return {"message": "Result uploaded"}
