"""Tests for FileInfo and other file manager client data models."""
from src.network.file_manager.client import FileInfo


def test_fileinfo_has_metadata_default_empty_dict():
    fi = FileInfo(id="x", name="y", is_folder=False)
    assert fi.metadata == {}


def test_fileinfo_metadata_is_per_instance_not_shared():
    """Guard against the classic mutable-default-argument bug."""
    a = FileInfo(id="1", name="a", is_folder=False)
    b = FileInfo(id="2", name="b", is_folder=False)
    a.metadata["key"] = "value"
    assert b.metadata == {}


def test_fileinfo_accepts_explicit_metadata():
    fi = FileInfo(id="x", name="y", is_folder=False, metadata={"nb_downloads": 42})
    assert fi.metadata["nb_downloads"] == 42
