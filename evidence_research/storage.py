from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class ResearchJob:
    id: str
    status: str
    cache_key: str
    request: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "task_id": self.id,
            "status": self.status,
            "request": self.request,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.result is not None:
            payload["result"] = self.result
        return payload


class TaskStateStore:
    """SQLite-backed task history and result cache."""

    def __init__(self, path: str | Path = "data/research.db") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._memory_connection: sqlite3.Connection | None = None
        if self.path == ":memory:":
            self._memory_connection = sqlite3.connect(self.path, timeout=30)
            self._memory_connection.row_factory = sqlite3.Row
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_connection is not None:
            self._memory_connection.execute("PRAGMA busy_timeout = 30000")
            return self._memory_connection
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            if self.path != ":memory:":
                connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    cache_key TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_research_jobs_cache
                ON research_jobs(cache_key, status, updated_at)
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _encode(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)

    @staticmethod
    def _decode(value: str | None) -> Any:
        return json.loads(value) if value is not None else None

    @classmethod
    def _from_row(cls, row: sqlite3.Row) -> ResearchJob:
        return ResearchJob(
            id=str(row["id"]),
            status=str(row["status"]),
            cache_key=str(row["cache_key"]),
            request=cls._decode(row["request_json"]),
            result=cls._decode(row["result_json"]),
            error=row["error"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def create(self, *, request: dict[str, Any], cache_key: str) -> ResearchJob:
        task_id = uuid4().hex
        now = self._now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_jobs
                    (id, status, cache_key, request_json, created_at, updated_at)
                VALUES (?, 'queued', ?, ?, ?, ?)
                """,
                (task_id, cache_key, self._encode(request), now, now),
            )
        job = self.get(task_id)
        if job is None:
            raise RuntimeError(f"failed to create research task: {task_id}")
        return job

    def get(self, task_id: str) -> ResearchJob | None:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM research_jobs WHERE id = ?", (task_id,)).fetchone()
        return self._from_row(row) if row else None

    def find_cached(self, cache_key: str) -> ResearchJob | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM research_jobs
                WHERE cache_key = ? AND status = 'completed' AND result_json IS NOT NULL
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (cache_key,),
            ).fetchone()
        return self._from_row(row) if row else None

    def find_active(self, cache_key: str) -> ResearchJob | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM research_jobs
                WHERE cache_key = ? AND status IN ('queued', 'running')
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (cache_key,),
            ).fetchone()
        return self._from_row(row) if row else None

    def mark_running(self, task_id: str) -> ResearchJob:
        return self._update(task_id, status="running", error=None)

    def mark_completed(self, task_id: str, result: dict[str, Any]) -> ResearchJob:
        return self._update(
            task_id,
            status="completed",
            result_json=self._encode(result),
            error=None,
        )

    def mark_failed(self, task_id: str, error: str) -> ResearchJob:
        return self._update(task_id, status="failed", error=error)

    def _update(self, task_id: str, **fields: str | None) -> ResearchJob:
        allowed = {"status", "result_json", "error"}
        if not set(fields).issubset(allowed):
            raise ValueError("unsupported task fields")
        assignments = [f"{name} = ?" for name in fields]
        values: list[str | None] = list(fields.values())
        assignments.append("updated_at = ?")
        values.append(self._now())
        values.append(task_id)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE research_jobs SET {', '.join(assignments)} WHERE id = ?", values
            )
            if cursor.rowcount != 1:
                raise KeyError(f"unknown research task: {task_id}")
        job = self.get(task_id)
        if job is None:
            raise KeyError(f"unknown research task: {task_id}")
        return job

    def list(self, *, limit: int = 20) -> list[ResearchJob]:
        limit = min(max(limit, 1), 100)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM research_jobs ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._from_row(row) for row in rows]
