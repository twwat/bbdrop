"""Tests for cover photo data model fields on GalleryQueueItem."""
import pytest
from src.storage.queue_manager import GalleryQueueItem, QueueManager


class TestCoverFields:
    """Cover fields exist on GalleryQueueItem with correct defaults."""

    def test_cover_source_path_defaults_none(self):
        item = GalleryQueueItem(path="/tmp/test")
        assert item.cover_source_path is None

    def test_cover_host_id_defaults_none(self):
        item = GalleryQueueItem(path="/tmp/test")
        assert item.cover_host_id is None

    def test_cover_result_defaults_none(self):
        item = GalleryQueueItem(path="/tmp/test")
        assert item.cover_result is None

    def test_cover_fields_set_explicitly(self):
        item = GalleryQueueItem(
            path="/tmp/test",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="imx",
            cover_result={"bbcode": "[img]url[/img]", "image_url": "url", "thumb_url": "thumb"},
        )
        assert item.cover_source_path == "/tmp/test/cover.jpg"
        assert item.cover_host_id == "imx"
        assert item.cover_result["bbcode"] == "[img]url[/img]"


class TestCoverPersistence:
    """Cover fields survive round-trip through _item_to_dict / _dict_to_item."""

    def test_item_to_dict_includes_cover_fields(self):
        from unittest.mock import patch, MagicMock
        with patch('src.storage.queue_manager.QueueStore'), \
             patch('src.storage.queue_manager.QSettings'), \
             patch('src.storage.queue_manager.QObject.__init__'):
            qm = QueueManager.__new__(QueueManager)
            qm.items = {}
            qm.mutex = MagicMock()

            item = GalleryQueueItem(
                path="/tmp/test",
                cover_source_path="/tmp/test/cover.jpg",
                cover_host_id="imx",
                cover_result={"bbcode": "[img]x[/img]", "image_url": "x", "thumb_url": "t"},
            )
            d = qm._item_to_dict(item)
            assert d["cover_source_path"] == "/tmp/test/cover.jpg"
            assert d["cover_host_id"] == "imx"
            assert d["cover_result"]["bbcode"] == "[img]x[/img]"

    def test_dict_to_item_restores_cover_fields(self):
        from unittest.mock import patch, MagicMock
        with patch('src.storage.queue_manager.QueueStore'), \
             patch('src.storage.queue_manager.QSettings'), \
             patch('src.storage.queue_manager.QObject.__init__'):
            qm = QueueManager.__new__(QueueManager)
            qm._next_order = 0

            data = {
                "path": "/tmp/test",
                "status": "ready",
                "cover_source_path": "/tmp/test/cover.jpg",
                "cover_host_id": "imx",
                "cover_result": {"bbcode": "[img]x[/img]"},
            }
            item = qm._dict_to_item(data)
            assert item.cover_source_path == "/tmp/test/cover.jpg"
            assert item.cover_host_id == "imx"
            assert item.cover_result == {"bbcode": "[img]x[/img]"}

    def test_dict_to_item_cover_defaults_none(self):
        from unittest.mock import patch, MagicMock
        with patch('src.storage.queue_manager.QueueStore'), \
             patch('src.storage.queue_manager.QSettings'), \
             patch('src.storage.queue_manager.QObject.__init__'):
            qm = QueueManager.__new__(QueueManager)
            qm._next_order = 0

            data = {"path": "/tmp/test", "status": "ready"}
            item = qm._dict_to_item(data)
            assert item.cover_source_path is None
            assert item.cover_host_id is None
            assert item.cover_result is None
