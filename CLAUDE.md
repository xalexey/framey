# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VisiTrack is a vehicle detection and counting API. It processes uploaded videos using YOLOv8 + SORT tracking to count vehicles crossing a defined line. Built with FastAPI + SQLite.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database (creates tables, adds test user with api_key: test-key)
python init_db.py

# Run the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run the distributed worker (points to a running server instance)
python worker.py --server http://localhost:8000 --api-key YOUR_API_KEY [--interval 5]
```

No test suite or linter is configured.

## Architecture

### Request Flow

1. Client authenticates via `X-Api-Key` header (64-char hex token)
2. Admin grants camera permissions to users (`camera_permissions` table)
3. User uploads a video for a specific `camera_code` → stored with UUID filename under `uploads/`
4. User calls `/api/process?file_id=UUID` → task created in `tasks` table
5. **If `use_worker=false`**: FastAPI background task runs `process_video()` on the server
6. **If `use_worker=true`**: Task queued; external `worker.py` polls `/api/worker/tasks`, downloads file, processes, and POSTs results back
7. Processed video saved to `output/`; task status updates to `done` with `car_count`

### Code Layout

- **`app/main.py`** — All FastAPI route handlers. Endpoints are grouped: user management, upload/process/download, camera settings, permissions (admin-only), admin management, worker API.
- **`app/database.py`** — All SQLite operations. Direct SQL via `sqlite3`, WAL mode enabled. Contains migration logic for schema evolution (e.g., global camera settings migrated from per-user).
- **`app/processing.py`** — `process_video()`: uses YOLOv8n for vehicle detection, SORT for tracking, counts objects crossing a line defined by `ax - y + b = 0` with offset tolerance. Processes every 2nd frame. Reports progress in 5% increments via callback.
- **`app/auth.py`** — `get_current_user()` dependency: validates `X-Api-Key` header against `users` table.
- **`sort.py`** — SORT tracking algorithm (external, not project-authored).
- **`worker.py`** — Standalone script for GPU machines. Polls server for pending tasks, downloads video, calls `process_video()` locally, uploads result.

### Database Schema (SQLite)

Key relationships:
- `users` ← `camera_permissions` (many-to-many via `camera_code`)
- `users` ← `files` ← `tasks`
- `camera_settings` keyed by `camera_code` (UUID string, global — not per-user)
- `admins` is a subset of `users`

Camera `use_worker` flag determines local vs. distributed processing.

### Video Processing Details

- Model: `yolov8n.pt` (must be present at repo root, git-ignored)
- Default vehicle class: `class_id=2` (COCO car class)
- Line equation: `a*x - y + b = 0`; objects counted when they cross within `±offset` pixels
- SORT params: `max_age=20`, `min_hits=3`, `iou_threshold=0.3`
- Frame skipping: every 2nd frame processed for speed

### Authentication & Authorization

- All endpoints except `POST /api/users` require `X-Api-Key`
- Camera access is gated by `camera_permissions` (admin grants per-user per-camera)
- Admin endpoints (`/api/permissions`, `/api/admins`) require the caller to be in `admins` table
- Worker endpoints (`/api/worker/*`) require a valid API key with no additional restrictions
