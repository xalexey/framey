import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "visitrack.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_tables():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY REFERENCES users(id),
            line_y INTEGER NOT NULL DEFAULT 400,
            offset INTEGER NOT NULL DEFAULT 6,
            confidence REAL NOT NULL DEFAULT 0.5,
            car_class_id INTEGER NOT NULL DEFAULT 2
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            status TEXT NOT NULL DEFAULT 'pending',
            filename TEXT NOT NULL,
            car_count INTEGER,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            finished_at TEXT
        );
    """)
    conn.commit()
    conn.close()


def get_user_by_api_key(api_key: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE api_key = ?", (api_key,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_user_settings(user_id: int) -> dict:
    conn = get_connection()
    row = conn.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"user_id": user_id, "line_y": 400, "offset": 6, "confidence": 0.5, "car_class_id": 2}


def update_user_settings(user_id: int, settings: dict):
    conn = get_connection()
    conn.execute("""
        INSERT INTO user_settings (user_id, line_y, offset, confidence, car_class_id)
        VALUES (:user_id, :line_y, :offset, :confidence, :car_class_id)
        ON CONFLICT(user_id) DO UPDATE SET
            line_y = :line_y,
            offset = :offset,
            confidence = :confidence,
            car_class_id = :car_class_id
    """, {"user_id": user_id, **settings})
    conn.commit()
    conn.close()


def create_task(task_id: str, user_id: int, filename: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO tasks (id, user_id, status, filename) VALUES (?, ?, 'pending', ?)",
        (task_id, user_id, filename),
    )
    conn.commit()
    conn.close()


def update_task_status(task_id: str, status: str, car_count: int | None = None, error_message: str | None = None):
    conn = get_connection()
    finished_at = datetime.utcnow().isoformat() if status in ("done", "error") else None
    conn.execute(
        "UPDATE tasks SET status = ?, car_count = ?, error_message = ?, finished_at = ? WHERE id = ?",
        (status, car_count, error_message, finished_at, task_id),
    )
    conn.commit()
    conn.close()


def get_task(task_id: str, user_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_tasks_for_user(user_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
