from pathlib import Path

import pytest

from app.utils.paths import is_within, resolve_safe_directory, validate_directory_writable


class TestResolveSafeDirectory:
    def test_resolves_relative_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        resolved = resolve_safe_directory("subdir")
        assert resolved == (tmp_path / "subdir").resolve()

    def test_expands_home(self):
        resolved = resolve_safe_directory("~")
        assert resolved.is_absolute()

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            resolve_safe_directory("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            resolve_safe_directory("   ")


class TestValidateDirectoryWritable:
    def test_creates_missing_directory(self, tmp_path):
        target = tmp_path / "new_folder"
        ok, reason = validate_directory_writable(target)
        assert ok is True
        assert reason is None
        assert target.is_dir()

    def test_existing_writable_directory(self, tmp_path):
        ok, reason = validate_directory_writable(tmp_path)
        assert ok is True

    def test_rejects_a_file_path(self, tmp_path):
        file_path = tmp_path / "not_a_dir.txt"
        file_path.write_text("hello")
        ok, reason = validate_directory_writable(file_path)
        assert ok is False
        assert reason is not None


class TestIsWithin:
    def test_child_within_parent(self, tmp_path):
        child = tmp_path / "a" / "b"
        child.mkdir(parents=True)
        assert is_within(child, tmp_path)

    def test_sibling_not_within(self, tmp_path):
        sibling = tmp_path.parent / "totally_unrelated_dir_xyz"
        assert not is_within(sibling, tmp_path)
