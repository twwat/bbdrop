"""IMG-5: resuming after an app restart must skip images recorded in the DB."""

from unittest.mock import MagicMock, Mock, patch

from src.storage.queue_manager import GalleryQueueItem

ROWS = [
    ("a.jpg", {'image_url': 'https://h/i/a', 'thumb_url': '', 'size_bytes': 1, 'width': 0, 'height': 0}),
    ("b.jpg", {'image_url': 'https://h/i/b', 'thumb_url': '', 'size_bytes': 1, 'width': 0, 'height': 0}),
]


def _worker(rows=None, error=None):
    from src.processing.upload_workers import UploadWorker
    queue_manager = Mock()
    if error:
        queue_manager.store.get_uploaded_images.side_effect = error
    else:
        queue_manager.store.get_uploaded_images.return_value = rows or []
    with patch('src.processing.upload_workers.RenameWorker'):
        worker = UploadWorker(queue_manager)
    worker.rename_worker = MagicMock()
    worker.global_byte_counter = MagicMock()
    worker.current_gallery_counter = MagicMock()
    worker.progress_updated = MagicMock()
    worker._bw_last_bytes = 0
    worker._bw_last_time = 0
    return worker, queue_manager


def _run(worker, item):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {'successful_count': 0, 'total_images': 3, 'images': []}

    with patch('src.processing.upload_workers.UploadEngine') as engine_cls:
        engine_cls.return_value.run.side_effect = fake_run
        worker.current_item = item
        worker._run_upload_engine(item, thumbnail_size=350, thumbnail_format=2,
                                  max_retries=3, parallel_batch_size=5)
    return captured


def test_resume_after_restart_skips_images_recorded_in_db():
    worker, queue_manager = _worker(ROWS)
    item = GalleryQueueItem(path="/tmp/g", name="g", gallery_id="G1", uploaded_images=2)

    captured = _run(worker, item)

    queue_manager.store.get_uploaded_images.assert_called_once_with("/tmp/g")
    assert captured['already_uploaded'] == {"a.jpg", "b.jpg"}
    assert captured['existing_gallery_id'] == "G1"
    assert item.uploaded_images_data == ROWS


def test_no_restore_without_gallery_id():
    worker, queue_manager = _worker(ROWS)
    item = GalleryQueueItem(path="/tmp/g", name="g", gallery_id="", uploaded_images=2)

    captured = _run(worker, item)

    queue_manager.store.get_uploaded_images.assert_not_called()
    assert captured['already_uploaded'] == set()


def test_no_restore_when_nothing_uploaded_yet():
    worker, queue_manager = _worker(ROWS)
    item = GalleryQueueItem(path="/tmp/g", name="g", gallery_id="G1", uploaded_images=0)

    _run(worker, item)

    queue_manager.store.get_uploaded_images.assert_not_called()


def test_in_memory_state_wins_over_db():
    worker, queue_manager = _worker(ROWS)
    item = GalleryQueueItem(path="/tmp/g", name="g", gallery_id="G1", uploaded_images=1)
    item.uploaded_files = {"a.jpg"}

    captured = _run(worker, item)

    queue_manager.store.get_uploaded_images.assert_not_called()
    assert captured['already_uploaded'] == {"a.jpg"}


def test_db_error_falls_back_to_full_upload():
    worker, _ = _worker(error=Exception("database is locked"))
    item = GalleryQueueItem(path="/tmp/g", name="g", gallery_id="G1", uploaded_images=2)

    captured = _run(worker, item)

    assert captured['already_uploaded'] == set()
