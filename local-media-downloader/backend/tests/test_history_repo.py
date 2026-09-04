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
