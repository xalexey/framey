import sqlite3
import os
import secrets
from datetime import datetime, UTC

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

        CREATE TABLE IF NOT EXISTS camera_settings (
            camera_code TEXT PRIMARY KEY,
            a REAL NOT NULL DEFAULT 0,
            b REAL NOT NULL DEFAULT 400,
            offset INTEGER NOT NULL DEFAULT 6,
            confidence REAL NOT NULL DEFAULT 0.5,
            car_class_id INTEGER NOT NULL DEFAULT 2,
            use_worker INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS camera_permissions (
            user_id INTEGER NOT NULL REFERENCES users(id),
            camera_code TEXT NOT NULL,
            PRIMARY KEY (user_id, camera_code)
        );

        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS files (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            camera_code TEXT NOT NULL,
            filename TEXT NOT NULL,
            upload_path TEXT NOT NULL,
            output_path TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            camera_code TEXT NOT NULL,
            file_id TEXT REFERENCES files(id),
            status TEXT NOT NULL DEFAULT 'pending',
            filename TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            car_count INTEGER,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            started_at TEXT,
            finished_at TEXT
        );
    """)
    conn.commit()
    conn.close()
    _migrate_tasks_table()
    _migrate_camera_settings_v2()
    _migrate_tasks_started_at()


def _migrate_tasks_table():
    conn = get_connection()
    cursor = conn.execute("PRAGMA table_info(tasks)")
    columns = [row[1] for row in cursor.fetchall()]
    if "file_id" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN file_id TEXT REFERENCES files(id)")
    if "progress" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN progress INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    conn.close()


def _migrate_tasks_started_at():
    conn = get_connection()
    cursor = conn.execute("PRAGMA table_info(tasks)")
    columns = [row[1] for row in cursor.fetchall()]
    if "started_at" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN started_at TEXT")
        conn.commit()
    conn.close()


def _migrate_camera_settings_v2():
    """Migrate camera_settings from per-user schema to global schema with separate permissions table."""
    conn = get_connection()
    cursor = conn.execute("PRAGMA table_info(camera_settings)")
    columns = [row[1] for row in cursor.fetchall()]

    if "user_id" not in columns:
        # Already on new schema or fresh install
        conn.close()
        return

    # Old schema detected — ensure use_worker column exists before migration
    if "use_worker" not in columns:
        conn.execute("ALTER TABLE camera_settings ADD COLUMN use_worker INTEGER NOT NULL DEFAULT 0")
        conn.commit()

    # Recreate camera_settings without user_id, migrate permissions to separate table
    conn.executescript("""
        CREATE TABLE camera_settings_new (
            camera_code TEXT PRIMARY KEY,
            a REAL NOT NULL DEFAULT 0,
            b REAL NOT NULL DEFAULT 400,
            offset INTEGER NOT NULL DEFAULT 6,
            confidence REAL NOT NULL DEFAULT 0.5,
            car_class_id INTEGER NOT NULL DEFAULT 2,
            use_worker INTEGER NOT NULL DEFAULT 0
        );

        INSERT OR IGNORE INTO camera_settings_new (camera_code, a, b, offset, confidence, car_class_id, use_worker)
        SELECT camera_code, a, b, offset, confidence, car_class_id, use_worker
        FROM camera_settings;

        CREATE TABLE IF NOT EXISTS camera_permissions (
            user_id INTEGER NOT NULL REFERENCES users(id),
            camera_code TEXT NOT NULL,
            PRIMARY KEY (user_id, camera_code)
        );

        INSERT OR IGNORE INTO camera_permissions (user_id, camera_code)
        SELECT user_id, camera_code FROM camera_settings;

        DROP TABLE camera_settings;
        ALTER TABLE camera_settings_new RENAME TO camera_settings;
    """)
    conn.close()


def create_user(name: str) -> dict:
    api_key = secrets.token_hex(32)
    conn = get_connection()
    conn.execute(
        "INSERT INTO users (api_key, name) VALUES (?, ?)",
        (api_key, name),
    )
    conn.commit()
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"id": user_id, "name": name, "api_key": api_key}


def get_user_by_api_key(api_key: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE api_key = ?", (api_key,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_camera_settings(camera_code: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM camera_settings WHERE camera_code = ?",
        (camera_code,),
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def update_camera_settings(camera_code: str, settings: dict):
    conn = get_connection()
    conn.execute("""
        INSERT INTO camera_settings (camera_code, a, b, offset, confidence, car_class_id, use_worker)
        VALUES (:camera_code, :a, :b, :offset, :confidence, :car_class_id, :use_worker)
        ON CONFLICT(camera_code) DO UPDATE SET
            a = :a,
            b = :b,
            offset = :offset,
            confidence = :confidence,
            car_class_id = :car_class_id,
            use_worker = :use_worker
    """, {"camera_code": camera_code, **settings})
    conn.commit()
    conn.close()


def check_camera_permission(user_id: int, camera_code: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM camera_permissions WHERE user_id = ? AND camera_code = ?",
        (user_id, camera_code),
    ).fetchone()
    conn.close()
    return row is not None


def grant_camera_permission(user_id: int, camera_code: str):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO camera_permissions (user_id, camera_code) VALUES (?, ?)",
        (user_id, camera_code),
    )
    conn.commit()
    conn.close()


def revoke_camera_permission(user_id: int, camera_code: str):
    conn = get_connection()
    conn.execute(
        "DELETE FROM camera_permissions WHERE user_id = ? AND camera_code = ?",
        (user_id, camera_code),
    )
    conn.commit()
    conn.close()


def get_user_cameras(user_id: int) -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT camera_code FROM camera_permissions WHERE user_id = ? ORDER BY camera_code",
        (user_id,),
    ).fetchall()
    conn.close()
    return [row[0] for row in rows]


def is_admin(user_id: int) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row is not None


def add_admin(user_id: int):
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()


def remove_admin(user_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_admins() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT u.id, u.name FROM admins a JOIN users u ON u.id = a.user_id ORDER BY u.id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_file(file_id: str, user_id: int, camera_code: str, filename: str, upload_path: str, output_path: str | None = None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO files (id, user_id, camera_code, filename, upload_path, output_path) VALUES (?, ?, ?, ?, ?, ?)",
        (file_id, user_id, camera_code, filename, upload_path, output_path),
    )
    conn.commit()
    conn.close()


def get_file(file_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def update_file_output_path(file_id: str, output_path: str):
    conn = get_connection()
    conn.execute("UPDATE files SET output_path = ? WHERE id = ?", (output_path, file_id))
    conn.commit()
    conn.close()


def create_task(task_id: str, user_id: int, camera_code: str, filename: str, file_id: str | None = None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO tasks (id, user_id, camera_code, file_id, status, filename) VALUES (?, ?, ?, ?, 'pending', ?)",
        (task_id, user_id, camera_code, file_id, filename),
    )
    conn.commit()
    conn.close()


def update_task_progress(task_id: str, progress: int):
    conn = get_connection()
    if progress == -1:
        now = datetime.now(UTC)
        conn.execute("UPDATE tasks SET progress = ?, started_at = ? WHERE id = ?", (0, now, task_id))
    else:
        conn.execute("UPDATE tasks SET progress = ? WHERE id = ?", (progress, task_id))
    conn.commit()
    conn.close()


def update_task_status(task_id: str, status: str, car_count: int | None = None, error_message: str | None = None):
    conn = get_connection()
    #now = datetime.utcnow().isoformat()
    now = datetime.now(UTC)
    #started_at = now if status == "processing" else None
    finished_at = now if status in ("done", "error") else None
    #conn.execute(
    #    """UPDATE tasks SET status = ?, car_count = ?, error_message = ?, finished_at = ?,
    #       started_at = COALESCE(CASE WHEN ? IS NOT NULL THEN ? ELSE started_at END, started_at)
    #       WHERE id = ?""",
    #    (status, car_count, error_message, finished_at, started_at, started_at, task_id),
    #)
    conn.execute(
        """UPDATE tasks SET status = ?, car_count = ?, error_message = ?, finished_at = ? WHERE id = ?""",
        (status, car_count, error_message, finished_at, task_id),
    )
    conn.commit()
    conn.close()


def get_task(task_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
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


def get_pending_task() -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None
