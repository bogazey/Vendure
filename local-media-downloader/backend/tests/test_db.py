import sqlite3

from app.database.db import database_healthy, get_connection


class TestDatabaseCreation:
    def test_creates_schema_on_first_connection(self, tmp_path):
        db_path = tmp_path / "fresh.db"
        conn = get_connection(db_path)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "settings" in tables
        assert "history" in tables

    def test_reuses_connection_for_same_path(self, tmp_path):
        db_path = tmp_path / "reuse.db"
        first = get_connection(db_path)
        second = get_connection(db_path)
        assert first is second

    def test_history_table_has_expected_columns(self, tmp_path):
        db_path = tmp_path / "cols.db"
        conn = get_connection(db_path)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(history)").fetchall()}
        expected = {
            "id", "url", "platform", "title", "uploader", "thumbnail",
            "format_label", "resolution", "filepath", "filesize",
            "created_at", "completed_at", "status", "error_message", "request_json",
        }
        assert expected.issubset(columns)

    def test_database_healthy_reports_true_for_valid_db(self, tmp_path):
        db_path = tmp_path / "healthy.db"
        get_connection(db_path)
        assert database_healthy(db_path) is True

    def test_database_healthy_reports_false_for_broken_db(self, tmp_path):
        db_path = tmp_path / "broken.db"
        db_path.write_text("not a real sqlite database")
        assert database_healthy(db_path) is False
