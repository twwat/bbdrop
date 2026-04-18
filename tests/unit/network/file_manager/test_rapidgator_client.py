"""Tests for RapidgatorFileManagerClient parsers."""
from src.network.file_manager.rapidgator_client import RapidgatorFileManagerClient


def test_parse_file_copies_raw_dict_into_metadata():
    raw = {
        "file_id": "abc123",
        "mode": 0,
        "mode_label": "Public",
        "folder_id": "5106611",
        "name": "test.zip",
        "hash": "deadbeef",
        "size": 147,
        "created": 1775273358,
        "url": "https://rapidgator.net/file/abc123/test.zip.html",
        "nb_downloads": 42,
    }
    fi = RapidgatorFileManagerClient._parse_file(raw)
    assert fi.metadata == raw
    assert fi.metadata["nb_downloads"] == 42
    assert fi.metadata["url"] == "https://rapidgator.net/file/abc123/test.zip.html"
    assert fi.metadata["mode_label"] == "Public"


def test_parse_folder_copies_raw_dict_into_metadata():
    raw = {
        "folder_id": "7686821",
        "mode": 0,
        "mode_label": "Public",
        "parent_folder_id": "5106611",
        "name": "test",
        "url": "https://rapidgator.net/folder/7686821/test.html",
        "nb_folders": 3,
        "nb_files": 10,
        "size_files": 4951733274,
        "created": 1775704734,
    }
    fi = RapidgatorFileManagerClient._parse_folder(raw)
    assert fi.metadata == raw
    assert fi.metadata["nb_files"] == 10
    assert fi.metadata["nb_folders"] == 3
    assert fi.metadata["size_files"] == 4951733274


def test_parse_file_metadata_is_independent_copy():
    """Mutating metadata must not mutate the source dict."""
    raw = {"file_id": "x", "name": "y", "nb_downloads": 1}
    fi = RapidgatorFileManagerClient._parse_file(raw)
    fi.metadata["nb_downloads"] = 999
    assert raw["nb_downloads"] == 1
