"""History table access."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from app.database.db import get_cursor
from app.models.schemas import HistoryRecordOut

# Statuses that mean "still in progress" — a history row left in one of these
# states after a restart means the app was killed mid-download.
_NON_TERMINAL_STATUSES = ("queued", "analyzing", "downloading", "merging", "converting")


def _row_to_record(row: sqlite3.Row) -> HistoryRecordOut:
    return HistoryRecordOut(
        id=row["id"],
        url=row["url"],
        platform=row["platform"],
        title=row["title"],
        uploader=row["uploader"],
        thumbnail=row["thumbnail"],
        format_label=row["format_label"],
        resolution=row["resolution"],
        filepath=row["filepath"],
        filesize=row["filesize"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        status=row["status"],
        error_message=row["error_message"],
    )


def upsert(record: dict) -> None:
    record = {"request_json": None, "user_id": None, **record}
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO history (
                id, url, platform, title, uploader, thumbnail, format_label,
                resolution, filepath, filesize, created_at, completed_at,
                status, error_message, request_json, user_id
            ) VALUES (:id, :url, :platform, :title, :uploader, :thumbnail,
                :format_label, :resolution, :filepath, :filesize, :created_at,
                :completed_at, :status, :error_message, :request_json, :user_id)
            ON CONFLICT(id) DO UPDATE SET
                url=excluded.url, platform=excluded.platform, title=excluded.title,
                uploader=excluded.uploader, thumbnail=excluded.thumbnail,
                format_label=excluded.format_label, resolution=excluded.resolution,
                filepath=excluded.filepath, filesize=excluded.filesize,
                completed_at=excluded.completed_at, status=excluded.status,
                error_message=excluded.error_message,
                request_json=COALESCE(excluded.request_json, history.request_json),
                user_id=COALESCE(history.user_id, excluded.user_id)
            """,
            record,
        )


def get_request_json(record_id: str) -> Optional[str]:
    with get_cursor() as cur:
        cur.execute("SELECT request_json FROM history WHERE id = ?", (record_id,))
        row = cur.fetchone()
    return row["request_json"] if row else None


def list_records(
    search: Optional[str] = None,
    platform: Optional[str] = None,
    status: Optional[str] = None,
    order: str = "newest",
    user_id: Optional[str] = None,
) -> list[HistoryRecordOut]:
    query = "SELECT * FROM history WHERE 1=1"
    params: list = []
    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
    if search:
        query += " AND (title LIKE ? OR uploader LIKE ? OR url LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])
    if platform:
        query += " AND platform = ?"
        params.append(platform)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at " + ("DESC" if order == "newest" else "ASC")

    with get_cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    return [_row_to_record(r) for r in rows]


def get(record_id: str, user_id: Optional[str] = None) -> Optional[HistoryRecordOut]:
    with get_cursor() as cur:
        if user_id is not None:
            cur.execute("SELECT * FROM history WHERE id = ? AND user_id = ?", (record_id, user_id))
        else:
            cur.execute("SELECT * FROM history WHERE id = ?", (record_id,))
        row = cur.fetchone()
    return _row_to_record(row) if row else None


def delete(record_id: str, user_id: Optional[str] = None) -> None:
    with get_cursor() as cur:
        if user_id is not None:
            cur.execute("DELETE FROM history WHERE id = ? AND user_id = ?", (record_id, user_id))
        else:
            cur.execute("DELETE FROM history WHERE id = ?", (record_id,))


def clear_all(user_id: Optional[str] = None) -> list[HistoryRecordOut]:
    with get_cursor() as cur:
        if user_id is not None:
            cur.execute("SELECT * FROM history WHERE user_id = ?", (user_id,))
            rows = [_row_to_record(r) for r in cur.fetchall()]
            cur.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        else:
            cur.execute("SELECT * FROM history")
            rows = [_row_to_record(r) for r in cur.fetchall()]
            cur.execute("DELETE FROM history")
    return rows


def filepath_exists(filepath: str, user_id: Optional[str] = None) -> bool:
    """Whether a history row currently references this exact file path.

    Used to allow opening/deleting a file from an older download after the
    user has since changed their download folder in Settings. Always pass
    `user_id` from an authenticated caller - without it this would let one
    account probe/act on whether *any other* account ever downloaded a file
    at a given path.
    """
    with get_cursor() as cur:
        if user_id is not None:
            cur.execute("SELECT 1 FROM history WHERE filepath = ? AND user_id = ? LIMIT 1", (filepath, user_id))
        else:
            cur.execute("SELECT 1 FROM history WHERE filepath = ? LIMIT 1", (filepath,))
        return cur.fetchone() is not None


def mark_interrupted_as_failed(message: str) -> int:
    """Mark any row still "in progress" as failed.

    Called once at startup: such rows mean the app was killed (crash, force
    quit) while a download was active. Marking them failed makes them show up
    clearly in History (rather than being stuck "downloading" forever) and
    retryable, instead of silently vanishing.
    """
    now = datetime.now(timezone.utc).isoformat()
    placeholders = ",".join("?" * len(_NON_TERMINAL_STATUSES))
    with get_cursor() as cur:
        cur.execute(
            f"""
            UPDATE history
            SET status = 'failed', error_message = ?, completed_at = COALESCE(completed_at, ?)
            WHERE status IN ({placeholders})
            """,
            (message, now, *_NON_TERMINAL_STATUSES),
        )
        return cur.rowcount
