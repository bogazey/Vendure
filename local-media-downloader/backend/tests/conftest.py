"""Test-wide setup: redirect all app data to a temp directory before anything imports app.config.paths."""
import os
import tempfile

_TEST_DATA_DIR = tempfile.mkdtemp(prefix="lmd_test_data_")
_TEST_DOWNLOAD_DIR = tempfile.mkdtemp(prefix="lmd_test_downloads_")

os.environ["LMD_DATA_DIR"] = _TEST_DATA_DIR
os.environ["LMD_LOG_DIR"] = os.path.join(_TEST_DATA_DIR, "logs")
os.environ["LMD_DB_PATH"] = os.path.join(_TEST_DATA_DIR, "app.db")
os.environ["LMD_DOWNLOAD_DIR"] = _TEST_DOWNLOAD_DIR
