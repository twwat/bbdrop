"""Tests for XFSFileManagerClient parsers."""
from src.network.file_manager.xfs_client import XFSFileManagerClient


def _make_client():
    # Bypass __init__ validation; _parse_file is effectively a method
    # that does not use self for most of its logic.
    c = XFSFileManagerClient.__new__(XFSFileManagerClient)
    c.host_id = "katfile"
    c._link_prefixes = {"katfile": "https://katfile.cloud/"}
    return c


def test_parse_file_copies_raw_dict_into_metadata():
    raw = {
        "file_code": "abc123",
        "file_title": "example.zip",
        "file_size": 1024,
        "file_md5": "deadbeef",
        "file_public": 1,
        "file_content_type": "application/zip",
        "created": "2024-08-26T00:00:00",
    }
    c = _make_client()
    fi = c._parse_file(raw)
    assert fi.metadata == raw
    assert fi.metadata["file_md5"] == "deadbeef"


def test_parse_folder_copies_raw_dict_into_metadata():
    raw = {"fld_id": "42", "name": "docs", "parent_id": "0"}
    fi = XFSFileManagerClient._parse_folder(raw)
    assert fi.metadata == raw
