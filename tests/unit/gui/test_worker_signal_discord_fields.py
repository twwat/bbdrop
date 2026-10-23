"""WorkerSignalHandler: file host notifications carry Discord message fields."""

import os
from unittest.mock import MagicMock, patch

from src.gui.worker_signal_handler import WorkerSignalHandler
from src.storage.queue_manager import GalleryQueueItem

GALLERY = os.path.normpath("C:/media/gallery one")


def _handler(wants_discord=True):
    mw = MagicMock()
    mw._get_current_tab_items.return_value = []
    mw.queue_manager.store.get_file_host_uploads_for_paths.return_value = {}
    mw.file_host_controller._db_id_to_path = {}
    item = GalleryQueueItem(path=GALLERY, name="gallery one")
    item.gallery_url = "https://imx.to/g/abc"
    mw.queue_manager.get_item.return_value = item
    mw.notification_manager.wants_discord.return_value = wants_discord
    return WorkerSignalHandler(mw), mw


def _notify_kwargs(mw, event):
    calls = [c for c in mw.notification_manager.notify.call_args_list if c.args[0] == event]
    assert len(calls) == 1
    return calls[0].kwargs


class TestCompleted:
    def test_completed_handler_passes_fields(self):
        h, mw = _handler()
        with patch('src.services.discord_message.filehost_fields',
                   return_value={'host_name': 'Rapidgator'}) as build:
            h.on_file_host_upload_completed(7, "rapidgator", {}, GALLERY)
        build.assert_called_once_with(
            mw.queue_manager.get_item.return_value, "rapidgator",
            mw.queue_manager.store, GALLERY, error='')
        assert _notify_kwargs(mw, 'filehost_upload_completed')['fields'] == {
            'host_name': 'Rapidgator'}

    def test_no_field_reads_when_discord_off(self):
        h, mw = _handler(wants_discord=False)
        with patch('src.services.discord_message.collect_file_host_links') as collect:
            h.on_file_host_upload_completed(7, "rapidgator", {}, GALLERY)
            h.on_file_host_upload_failed(7, "rapidgator", "boom", GALLERY)
        collect.assert_not_called()
        assert _notify_kwargs(mw, 'filehost_upload_completed')['fields'] is None
        assert _notify_kwargs(mw, 'filehost_upload_failed')['fields'] is None


class TestFailed:
    def test_failed_handler_passes_fields_and_rechecks_gallery(self):
        h, mw = _handler()
        with patch('src.services.discord_message.filehost_fields',
                   return_value={'error': 'boom'}) as build:
            h.on_file_host_upload_failed(7, "keep2share", "boom", GALLERY)
        build.assert_called_once_with(
            mw.queue_manager.get_item.return_value, "keep2share",
            mw.queue_manager.store, GALLERY, error="boom")
        kwargs = _notify_kwargs(mw, 'filehost_upload_failed')
        assert kwargs == {'detail': 'boom', 'fields': {'error': 'boom'}}
        mw.upload_lifecycle_handler.maybe_notify_gallery_done.assert_called_once_with(
            GALLERY, failed_host="keep2share")

    def test_gallery_recheck_error_is_contained(self):
        h, mw = _handler(wants_discord=False)
        mw.upload_lifecycle_handler.maybe_notify_gallery_done.side_effect = RuntimeError("x")
        h.on_file_host_upload_failed(7, "keep2share", "boom", GALLERY)   # must not raise
        mw.notification_manager.notify.assert_called()
