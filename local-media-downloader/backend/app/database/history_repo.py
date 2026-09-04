"""History table access."""
from __future__ import annotations

import sqlite3
from typing import Optional

from app.database.db import get_cursor
from app.models.schemas import HistoryRecordOut


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
    record = {"request_json": None, **record}
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO history (
                id, url, platform, title, uploader, thumbnail, format_label,
                resolution, filepath, filesize, created_at, completed_at,
                status, error_message, request_json
            ) VALUES (:id, :url, :platform, :title, :uploader, :thumbnail,
                :format_label, :resolution, :filepath, :filesize, :created_at,
                :completed_at, :status, :error_message, :request_json)
            ON CONFLICT(id) DO UPDATE SET
                url=excluded.url, platform=excluded.platform, title=excluded.title,
                uploader=excluded.uploader, thumbnail=excluded.thumbnail,
                format_label=excluded.format_label, resolution=excluded.resolution,
                filepath=excluded.filepath, filesize=excluded.filesize,
                completed_at=excluded.completed_at, status=excluded.status,
                error_message=excluded.error_message,
                request_json=COALESCE(excluded.request_json, history.request_json)
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
) -> list[HistoryRecordOut]:
    query = "SELECT * FROM history WHERE 1=1"
    params: list = []
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


def get(record_id: str) -> Optional[HistoryRecordOut]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM history WHERE id = ?", (record_id,))
        row = cur.fetchone()
    return _row_to_record(row) if row else None


def delete(record_id: str) -> None:
    with get_cursor() as cur:
        cur.execute("DELETE FROM history WHERE id = ?", (record_id,))


def clear_all() -> list[HistoryRecordOut]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM history")
        rows = [_row_to_record(r) for r in cur.fetchall()]
        cur.execute("DELETE FROM history")
    return rows
