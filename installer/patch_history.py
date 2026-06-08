from __future__ import annotations

import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / ".patch_history.db"
_LOCK = threading.Lock()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS patch_jobs (
            job_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            component_key TEXT NOT NULL,
            component_label TEXT NOT NULL,
            agent_type TEXT NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            search_root TEXT NOT NULL,
            archive_name TEXT NOT NULL,
            backup_suffix TEXT NOT NULL,
            status TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS patch_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            original_path TEXT NOT NULL,
            backup_path TEXT NOT NULL,
            display_name TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES patch_jobs(job_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_patch_jobs_lookup
        ON patch_jobs(host, port, search_root, component_key, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_patch_entries_job_id
        ON patch_entries(job_id);

        CREATE TABLE IF NOT EXISTS rollback_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rolled_back_at TEXT NOT NULL,
            component_key TEXT,
            component_label TEXT,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            search_root TEXT,
            original_path TEXT NOT NULL,
            used_backup_path TEXT NOT NULL,
            preserved_current_path TEXT,
            backup_suffix TEXT,
            status TEXT NOT NULL,
            job_id TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_rollback_logs_lookup
        ON rollback_logs(host, port, component_key, rolled_back_at DESC);
        """
    )
    existing_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(rollback_logs)").fetchall()
    }
    if "preserved_current_path" not in existing_columns:
        conn.execute(
            "ALTER TABLE rollback_logs ADD COLUMN preserved_current_path TEXT"
        )
    conn.commit()


def save_patch_job(
    *,
    component_key: str,
    component_label: str,
    agent_type: str,
    host: str,
    port: int,
    search_root: str,
    archive_name: str,
    backup_suffix: str,
    status: str,
    patched_entries: list[dict],
) -> dict | None:
    if not patched_entries:
        return None

    created_at = datetime.now(timezone.utc).isoformat()
    job_id = str(uuid.uuid4())

    with _LOCK:
        conn = _connect()
        try:
            _init_db(conn)
            conn.execute(
                """
                INSERT INTO patch_jobs (
                    job_id, created_at, component_key, component_label,
                    agent_type, host, port, search_root, archive_name,
                    backup_suffix, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    created_at,
                    component_key,
                    component_label,
                    agent_type,
                    host,
                    int(port),
                    search_root,
                    archive_name,
                    backup_suffix,
                    status,
                ),
            )
            conn.executemany(
                """
                INSERT INTO patch_entries (
                    job_id, filename, original_path, backup_path, display_name
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        job_id,
                        entry.get("filename", ""),
                        entry.get("original_path", ""),
                        entry.get("backup_path", ""),
                        entry.get("display_name") or entry.get("filename") or entry.get("original_path", "").split("/")[-1],
                    )
                    for entry in patched_entries
                    if entry.get("filename") and entry.get("original_path") and entry.get("backup_path")
                ],
            )
            conn.commit()
        finally:
            conn.close()

    return _load_job(job_id=job_id)


def find_recent_patch_job(
    *,
    host: str,
    port: int,
    search_root: str,
    component_key: str | None = None,
    job_id: str | None = None,
) -> dict | None:
    with _LOCK:
        conn = _connect()
        try:
            _init_db(conn)
            if job_id:
                return _load_job(job_id=job_id, conn=conn)

            query = """
                SELECT job_id
                FROM patch_jobs
                WHERE host = ? AND port = ? AND search_root = ?
            """
            params: list[object] = [host, int(port), search_root]
            if component_key:
                query += " AND component_key = ?"
                params.append(component_key)
            query += " ORDER BY created_at DESC LIMIT 1"

            row = conn.execute(query, params).fetchone()
            if not row:
                return None
            return _load_job(job_id=row["job_id"], conn=conn)
        finally:
            conn.close()


def list_recent_patch_jobs(
    *,
    host: str,
    port: int,
    search_root: str,
    component_key: str | None = None,
    limit: int = 10,
) -> list[dict]:
    with _LOCK:
        conn = _connect()
        try:
            _init_db(conn)
            query = """
                SELECT job_id
                FROM patch_jobs
                WHERE host = ? AND port = ? AND search_root = ?
            """
            params: list[object] = [host, int(port), search_root]
            if component_key:
                query += " AND component_key = ?"
                params.append(component_key)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(int(limit))

            rows = conn.execute(query, params).fetchall()
            return [
                _load_job(job_id=row["job_id"], conn=conn)
                for row in rows
                if row["job_id"]
            ]
        finally:
            conn.close()


def history_job_to_backups(job: dict) -> dict:
    result = {}
    suffix = job.get("backup_suffix", "")

    for entry in job.get("patched_entries", []):
        original_path = entry.get("original_path")
        backup_path = entry.get("backup_path")
        if not original_path or not backup_path:
            continue
        result.setdefault(original_path, []).append({
            "date": suffix,
            "label": _suffix_label(suffix),
            "backup_path": backup_path,
            "original_path": original_path,
            "display_name": entry.get("display_name") or entry.get("filename") or original_path.split("/")[-1],
        })

    return result


def save_rollback_logs(
    *,
    component_key: str | None,
    component_label: str | None,
    host: str,
    port: int,
    search_root: str | None,
    job_id: str | None,
    rollback_targets: list[dict],
    status: str,
) -> None:
    if not rollback_targets:
        return

    rolled_back_at = datetime.now(timezone.utc).isoformat()

    with _LOCK:
        conn = _connect()
        try:
            _init_db(conn)
            conn.executemany(
                """
                INSERT INTO rollback_logs (
                    rolled_back_at, component_key, component_label, host, port,
                    search_root, original_path, used_backup_path,
                    preserved_current_path, backup_suffix, status, job_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        rolled_back_at,
                        component_key,
                        component_label,
                        host,
                        int(port),
                        search_root,
                        target.get("original_path", ""),
                        target.get("backup_path", ""),
                        target.get("preserved_current_path"),
                        _extract_backup_suffix(target.get("backup_path", "")),
                        status,
                        job_id,
                    )
                    for target in rollback_targets
                    if target.get("original_path") and target.get("backup_path")
                ],
            )
            conn.commit()
        finally:
            conn.close()


def _load_job(*, job_id: str, conn: sqlite3.Connection | None = None) -> dict | None:
    owns_conn = conn is None
    if owns_conn:
        conn = _connect()
        _init_db(conn)

    try:
        job_row = conn.execute("SELECT * FROM patch_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if not job_row:
            return None

        entry_rows = conn.execute(
            """
            SELECT filename, original_path, backup_path, display_name
            FROM patch_entries
            WHERE job_id = ?
            ORDER BY id ASC
            """,
            (job_id,),
        ).fetchall()

        return {
            "job_id": job_row["job_id"],
            "created_at": job_row["created_at"],
            "component_key": job_row["component_key"],
            "component_label": job_row["component_label"],
            "agent_type": job_row["agent_type"],
            "host": job_row["host"],
            "port": int(job_row["port"]),
            "search_root": job_row["search_root"],
            "archive_name": job_row["archive_name"],
            "backup_suffix": job_row["backup_suffix"],
            "status": job_row["status"],
            "patched_entries": [
                {
                    "filename": row["filename"],
                    "original_path": row["original_path"],
                    "backup_path": row["backup_path"],
                    "display_name": row["display_name"],
                }
                for row in entry_rows
            ],
        }
    finally:
        if owns_conn:
            conn.close()


def _suffix_label(suffix: str) -> str:
    if suffix.startswith("bak") and len(suffix) == 9 and suffix[3:].isdigit():
        digits = suffix[3:]
        return f"20{digits[:2]}-{digits[2:4]}-{digits[4:6]}"
    if len(suffix) == 6 and suffix.isdigit():
        return f"20{suffix[:2]}-{suffix[2:4]}-{suffix[4:6]}"
    return suffix


def _extract_backup_suffix(backup_path: str) -> str | None:
    filename = backup_path.rsplit("/", 1)[-1]
    match = re.search(r"_bak(.+)$", filename)
    if not match:
        return None
    return match.group(1)
