from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: str | Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


class JobStore:
    def __init__(self, database_path: str | Path):
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    file_mtime REAL NOT NULL,
                    sha256 TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    category_id TEXT,
                    language TEXT,
                    privacy_status TEXT NOT NULL,
                    scheduled_at TEXT,
                    thumbnail_path TEXT,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT,
                    video_id TEXT,
                    video_url TEXT,
                    actual_privacy TEXT,
                    warning TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_queue
                    ON jobs(status, next_retry_at, created_at);
                CREATE TABLE IF NOT EXISTS watch_state (
                    file_path TEXT PRIMARY KEY,
                    file_size INTEGER NOT NULL,
                    file_mtime REAL NOT NULL,
                    sidecar_mtime REAL NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            # Requeue uploads interrupted by a process/Windows shutdown.
            db.execute(
                """UPDATE jobs SET status='retry_wait', next_retry_at=?, 
                   error='La aplicación se cerró durante la subida; se reintentará.',
                   updated_at=? WHERE status='uploading'""",
                (utc_now(), utc_now()),
            )

    def has_watch_version(
        self, file_path: str, file_size: int, file_mtime: float, sidecar_mtime: float
    ) -> bool:
        with self._connect() as db:
            row = db.execute(
                "SELECT file_size,file_mtime,sidecar_mtime FROM watch_state WHERE file_path=?",
                (file_path,),
            ).fetchone()
        return bool(
            row
            and row["file_size"] == file_size
            and row["file_mtime"] == file_mtime
            and row["sidecar_mtime"] == sidecar_mtime
        )

    def mark_watch_version(
        self, file_path: str, file_size: int, file_mtime: float, sidecar_mtime: float
    ) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO watch_state(file_path,file_size,file_mtime,sidecar_mtime,updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(file_path) DO UPDATE SET
                   file_size=excluded.file_size,file_mtime=excluded.file_mtime,
                   sidecar_mtime=excluded.sidecar_mtime,updated_at=excluded.updated_at""",
                (file_path, file_size, file_mtime, sidecar_mtime, utc_now()),
            )

    def add_job(self, metadata: dict[str, Any]) -> tuple[str, bool]:
        path = Path(metadata["file_path"])
        if not path.is_file():
            raise FileNotFoundError(path)
        stat = path.stat()
        file_hash = sha256_file(path)
        job_id = str(uuid.uuid4())
        now = utc_now()
        with self._connect() as db:
            cursor = db.execute(
                """
                INSERT OR IGNORE INTO jobs(
                    id,file_path,file_size,file_mtime,sha256,title,description,tags_json,
                    category_id,language,privacy_status,scheduled_at,thumbnail_path,
                    status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'queued',?,?)
                """,
                (
                    job_id,
                    str(path.resolve()),
                    stat.st_size,
                    stat.st_mtime,
                    file_hash,
                    metadata["title"],
                    metadata.get("description", ""),
                    json.dumps(metadata.get("tags", []), ensure_ascii=False),
                    metadata.get("category_id"),
                    metadata.get("language"),
                    metadata.get("privacy_status", "public"),
                    metadata.get("scheduled_at"),
                    metadata.get("thumbnail_path"),
                    now,
                    now,
                ),
            )
            if cursor.rowcount == 1:
                return job_id, True
            existing = db.execute("SELECT id FROM jobs WHERE sha256=?", (file_hash,)).fetchone()
            return (existing["id"] if existing else job_id), False

    def next_job(self) -> dict[str, Any] | None:
        now = utc_now()
        with self._connect() as db:
            row = db.execute(
                """SELECT * FROM jobs
                   WHERE status='queued'
                      OR (status='retry_wait' AND next_retry_at IS NOT NULL AND next_retry_at<=?)
                   ORDER BY created_at ASC LIMIT 1""",
                (now,),
            ).fetchone()
        return self._decode(row) if row else None

    def mark_uploading(self, job_id: str) -> None:
        with self._connect() as db:
            db.execute(
                """UPDATE jobs SET status='uploading',attempts=attempts+1,
                   next_retry_at=NULL,error=NULL,updated_at=? WHERE id=?""",
                (utc_now(), job_id),
            )

    def mark_completed(
        self, job_id: str, video_id: str, video_url: str,
        actual_privacy: str | None = None, warning: str | None = None,
        final_status: str = "published",
    ) -> None:
        with self._connect() as db:
            db.execute(
                """UPDATE jobs SET status=?,video_id=?,video_url=?,actual_privacy=?,
                   warning=?,error=NULL,next_retry_at=NULL,updated_at=? WHERE id=?""",
                (final_status, video_id, video_url, actual_privacy, warning, utc_now(), job_id),
            )

    def mark_failed(
        self, job_id: str, error: str, retryable: bool,
        retry_after_seconds: int | None = None, max_attempts: int = 5,
    ) -> None:
        with self._connect() as db:
            row = db.execute("SELECT attempts FROM jobs WHERE id=?", (job_id,)).fetchone()
            attempts = int(row["attempts"]) if row else max_attempts
            should_retry = retryable and attempts < max_attempts
            if should_retry:
                delay = retry_after_seconds or min(3600, 30 * (2 ** max(0, attempts - 1)))
                next_time = datetime.fromtimestamp(
                    datetime.now(timezone.utc).timestamp() + delay, timezone.utc
                ).isoformat()
                status = "retry_wait"
            else:
                next_time = None
                status = "failed"
            db.execute(
                """UPDATE jobs SET status=?,error=?,next_retry_at=?,updated_at=? WHERE id=?""",
                (status, error[:4000], next_time, utc_now(), job_id),
            )

    def retry_job(self, job_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                """UPDATE jobs SET status='queued',attempts=0,next_retry_at=NULL,
                   error=NULL,updated_at=? WHERE id=? AND status IN ('failed','retry_wait')""",
                (utc_now(), job_id),
            )
        return cursor.rowcount == 1

    def list_jobs(self, limit: int = 250) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._decode(row) for row in rows]

    def _decode(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["tags"] = json.loads(result.pop("tags_json"))
        return result
