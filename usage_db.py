import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_sqlite_path() -> str:
    path = (os.getenv("SQLITE_PATH") or "usage.db").strip()
    return path or "usage.db"


def init_db(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    with sqlite3.connect(db_path, timeout=30) as conn:
        # Use default rollback journal to avoid creating -wal/-shm side files.
        conn.execute("PRAGMA journal_mode=DELETE;")
        conn.execute("PRAGMA synchronous=FULL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS request_logs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts_utc TEXT NOT NULL,
              method TEXT NOT NULL,
              path TEXT NOT NULL,
              status_code INTEGER NOT NULL,
              duration_ms INTEGER NOT NULL,
              model TEXT,
              error_type TEXT
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_request_logs_ts ON request_logs(ts_utc);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_request_logs_path ON request_logs(path);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_request_logs_status ON request_logs(status_code);"
        )


@dataclass(frozen=True)
class RequestLogRow:
    method: str
    path: str
    status_code: int
    duration_ms: int
    model: str | None = None
    error_type: str | None = None
    ts_utc: str = ""


def log_request(db_path: str, row: RequestLogRow) -> None:
    ts_utc = row.ts_utc or _utc_now_iso()
    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.execute(
            """
            INSERT INTO request_logs (ts_utc, method, path, status_code, duration_ms, model, error_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts_utc,
                row.method,
                row.path,
                int(row.status_code),
                int(row.duration_ms),
                row.model,
                row.error_type,
            ),
        )


def usage_summary(
    db_path: str,
    since_seconds: int | None = None,
    limit_paths: int = 20,
) -> dict[str, Any]:
    where = ""
    params: tuple[Any, ...] = ()
    if since_seconds is not None and since_seconds > 0:
        cutoff = time.time() - since_seconds
        # On Windows, datetime.fromtimestamp() can raise OSError for out-of-range
        # timestamps (commonly negative values if since_seconds is huge).
        cutoff = max(0.0, float(cutoff))
        try:
            cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            cutoff_iso = ""

        if cutoff_iso:
            where = "WHERE ts_utc >= ?"
            params = (cutoff_iso,)

    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.row_factory = sqlite3.Row

        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM request_logs {where}", params
        ).fetchone()["n"]

        by_status = [
            dict(r)
            for r in conn.execute(
                f"""
                SELECT status_code, COUNT(*) AS n
                FROM request_logs
                {where}
                GROUP BY status_code
                ORDER BY n DESC
                """,
                params,
            ).fetchall()
        ]

        top_paths = [
            dict(r)
            for r in conn.execute(
                f"""
                SELECT path, method, COUNT(*) AS n, ROUND(AVG(duration_ms), 1) AS avg_ms
                FROM request_logs
                {where}
                GROUP BY path, method
                ORDER BY n DESC
                LIMIT ?
                """,
                (*params, int(limit_paths)),
            ).fetchall()
        ]

        errors = conn.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM request_logs
            {where + (" AND " if where else "WHERE ")} status_code >= 400
            """,
            params,
        ).fetchone()["n"]

        avg_ms = conn.execute(
            f"SELECT ROUND(AVG(duration_ms), 1) AS avg_ms FROM request_logs {where}",
            params,
        ).fetchone()["avg_ms"]

        return {
            "db_path": db_path,
            "since_seconds": since_seconds,
            "total_requests": total,
            "error_requests": errors,
            "avg_duration_ms": avg_ms,
            "by_status_code": by_status,
            "top_paths": top_paths,
        }

