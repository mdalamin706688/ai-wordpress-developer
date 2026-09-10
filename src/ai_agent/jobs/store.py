from __future__ import annotations

import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from ai_agent.config import get_settings
from ai_agent.jobs.schemas import JobRecord, JobStatus, utcnow


def _new_id() -> str:
    return "aij_" + uuid.uuid4().hex[:20]


class JobStore:
    def __init__(self, path: str | None = None) -> None:
        settings = get_settings()
        data_dir = Path(settings.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = Path(path) if path else data_dir / "jobs.db"
        self._lock = threading.Lock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def create(self, record: JobRecord) -> JobRecord:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO jobs (job_id, payload) VALUES (?, ?)",
                (record.job_id, record.model_dump_json()),
            )
            conn.commit()
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if not row:
            return None
        return JobRecord.model_validate_json(row["payload"])

    def find_by_idempotency(self, key: str) -> JobRecord | None:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM jobs").fetchall()
        for row in rows:
            rec = JobRecord.model_validate_json(row["payload"])
            if rec.idempotency_key == key:
                return rec
        return None

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        progress: str | None = None,
    ) -> JobRecord | None:
        with self._lock:
            rec = self.get(job_id)
            if not rec:
                return None
            if status:
                rec.status = status
            if result is not None:
                rec.result = result
            if error is not None:
                rec.error = error
            if progress is not None:
                rec.progress = progress
            rec.updated_at = utcnow()
            with self._connect() as conn:
                conn.execute(
                    "UPDATE jobs SET payload = ? WHERE job_id = ?",
                    (rec.model_dump_json(), job_id),
                )
                conn.commit()
            return rec

    @staticmethod
    def new_id() -> str:
        return _new_id()
