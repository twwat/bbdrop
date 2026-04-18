"""Tests for K2SFileManagerClient parsers."""
from src.network.file_manager.k2s_client import K2SFileManagerClient


def test_parse_file_info_copies_raw_dict_into_metadata():
    raw = {
        "id": "91239a7cee5c5",
        "name": "example.mp4",
        "is_available": True,
        "is_folder": False,
        "date_created": "2024-08-26 20:28:44",
        "size": 583224258,
        "md5": "992402f7cafbd9d671e7b44ac3462c57",
        "extended_info": {
            "abuses": [],
            "storage_object": "available",
            "size": 583224258,
            "date_download_last": "2024-08-26 20:28:44",
            "access": "public",
            "content_type": "video/mp4",
        },
    }
    fi = K2SFileManagerClient._parse_file_info(raw)
    assert fi.metadata == raw
    assert fi.metadata["extended_info"]["date_download_last"] == "2024-08-26 20:28:44"
    assert fi.metadata["extended_info"]["storage_object"] == "available"


def test_parse_file_info_survives_missing_extended_info():
    """getFilesInfo (not getFilesList) omits extended_info entirely."""
    raw = {
        "id": "abc",
        "name": "x.zip",
        "is_available": True,
        "is_folder": False,
        "size": 100,
        "md5": "d41d",
        "access": "public",
    }
    fi = K2SFileManagerClient._parse_file_info(raw)
    assert fi.metadata == raw
    assert "extended_info" not in fi.metadata


def test_parse_file_info_metadata_is_independent_copy():
    raw = {"id": "x", "name": "y", "is_folder": False, "extended_info": {"k": 1}}
    fi = K2SFileManagerClient._parse_file_info(raw)
    fi.metadata["extended_info"]["k"] = 999
    assert raw["extended_info"]["k"] == 1, "metadata must deep-copy nested dicts"
