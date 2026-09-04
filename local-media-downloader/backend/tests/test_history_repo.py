import uuid

from app.database import history_repo


def _make_record(**overrides):
    base = {
        "id": str(uuid.uuid4()),
        "url": "https://www.youtube.com/watch?v=abc123",
        "platform": "youtube",
        "title": "Test Video",
        "uploader": "Test Channel",
        "thumbnail": "https://example.com/t.jpg",
        "format_label": "1080p",
        "resolution": "1080p",
        "filepath": "/tmp/test.mp4",
        "filesize": 12345,
        "created_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:01:00+00:00",
        "status": "completed",
        "error_message": None,
        "request_json": None,
    }
    base.update(overrides)
    return base


class TestHistoryRepo:
    def test_upsert_and_get(self):
        record = _make_record()
        history_repo.upsert(record)
        fetched = history_repo.get(record["id"])
        assert fetched is not None
        assert fetched.title == "Test Video"

    def test_upsert_updates_existing_record(self):
        record = _make_record()
        history_repo.upsert(record)
        history_repo.upsert({**record, "status": "failed", "error_message": "boom"})
        fetched = history_repo.get(record["id"])
        assert fetched.status == "failed"
        assert fetched.error_message == "boom"

    def test_list_records_filters_by_platform(self):
        yt = _make_record(platform="youtube")
        tiktok = _make_record(platform="tiktok")
        history_repo.upsert(yt)
        history_repo.upsert(tiktok)
        results = history_repo.list_records(platform="tiktok")
        assert all(r.platform == "tiktok" for r in results)
        assert any(r.id == tiktok["id"] for r in results)

    def test_list_records_filters_by_search(self):
        record = _make_record(title="Unique Searchable Title 12345")
        history_repo.upsert(record)
        results = history_repo.list_records(search="Unique Searchable")
        assert any(r.id == record["id"] for r in results)

    def test_delete_removes_record(self):
        record = _make_record()
        history_repo.upsert(record)
        history_repo.delete(record["id"])
        assert history_repo.get(record["id"]) is None

    def test_get_request_json_roundtrip(self):
        record = _make_record(request_json='{"url": "https://example.com"}')
        history_repo.upsert(record)
        raw = history_repo.get_request_json(record["id"])
        assert raw == '{"url": "https://example.com"}'

    def test_filepath_exists_true_for_known_file(self):
        record = _make_record(filepath="/tmp/known-file.mp4")
        history_repo.upsert(record)
        assert history_repo.filepath_exists("/tmp/known-file.mp4") is True

    def test_filepath_exists_false_for_unknown_file(self):
        assert history_repo.filepath_exists("/tmp/never-downloaded.mp4") is False


class TestMarkInterruptedAsFailed:
    def test_marks_non_terminal_rows_as_failed(self):
        stuck = _make_record(status="downloading", completed_at=None)
        done = _make_record(status="completed")
        history_repo.upsert(stuck)
        history_repo.upsert(done)

        count = history_repo.mark_interrupted_as_failed("Interrupted by restart.")

        assert count >= 1
        recovered = history_repo.get(stuck["id"])
        assert recovered.status == "failed"
        assert recovered.error_message == "Interrupted by restart."
        assert recovered.completed_at is not None
        # Already-terminal rows must be left untouched.
        untouched = history_repo.get(done["id"])
        assert untouched.status == "completed"

    def test_is_a_noop_when_nothing_is_stuck(self):
        history_repo.upsert(_make_record(status="completed"))
        history_repo.upsert(_make_record(status="failed"))
        count = history_repo.mark_interrupted_as_failed("Interrupted by restart.")
        assert count == 0
