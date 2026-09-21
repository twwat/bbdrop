"""Progress signalling at split-archive part boundaries.

The pycurl progress callback restarts at 0 for each part, but nothing told
the GUI that. Consumers that carry a per-(gallery, host) live byte count --
ProgressTracker's byte-weighted percent -- therefore credited part N+1's
freshly created row with part N's final byte count until part N+1's first
throttled progress tick arrived, making the gallery percent jump up and then
fall back once per part boundary.

The worker now emits one un-throttled zero-progress signal as each part
starts, so every consumer's live count is reset at the boundary.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.processing.file_host_workers import FileHostWorker


@pytest.fixture
def parts(tmp_path):
    """Two real archive parts of different sizes."""
    p1 = tmp_path / "gallery.zip.001"
    p2 = tmp_path / "gallery.zip.002"
    p1.write_bytes(b"a" * 4096)
    p2.write_bytes(b"b" * 2048)
    return [p1, p2]


@pytest.fixture
def gallery(tmp_path):
    folder = tmp_path / "gallery"
    folder.mkdir()
    (folder / "image_0.jpg").write_bytes(b"x" * 128)
    return folder


def _run_two_part_upload(worker, gallery, parts, host_config):
    """Drive _process_upload over a two-part archive, reporting real progress."""
    def fake_upload(file_path, on_progress=None, should_stop=None, md5_hash=None):
        size = Path(file_path).stat().st_size
        if on_progress:
            # Mid-transfer, then complete -- spaced so the 0.25s throttle
            # doesn't swallow the final tick.
            on_progress(size // 2, size, 0.0)
        return {'status': 'success', 'url': 'https://host/f/x', 'file_id': 'x'}

    client = Mock()
    client.upload_file.side_effect = fake_upload
    # _update_session_from_client subscripts this directly -- a bare Mock
    # (or None) raises TypeError and aborts the run between parts.
    client.get_session_state.return_value = {
        'cookies': None, 'token': None, 'timestamp': 0,
    }

    with patch.object(worker, '_get_or_create_archive', return_value=parts), \
         patch.object(worker, '_create_client', return_value=client), \
         patch('src.processing.file_host_workers.get_file_host_setting', return_value=0), \
         patch('src.utils.paths.load_user_defaults', return_value={}), \
         patch('src.utils.metrics_store.get_metrics_store', return_value=Mock()):
        worker._process_upload(
            upload_id=1,
            db_id=123,
            gallery_path=str(gallery),
            gallery_name="Test",
            host_name="testhost",
            host_config=host_config,
        )


@patch('src.processing.file_host_workers.get_config_manager')
@patch('src.processing.file_host_workers.get_coordinator')
@patch('src.processing.file_host_workers.get_archive_manager')
@patch('src.processing.file_host_workers.QSettings')
def test_each_part_starts_with_a_zero_progress_emit(
    mock_qsettings, mock_archive_mgr, mock_coord, mock_config_mgr, gallery, parts
):
    host_config = Mock()
    host_config.name = "TestHost"
    host_config.require_file_hash = False
    mock_config_mgr.return_value.get_host.return_value = host_config

    store = Mock()
    store.get_file_host_uploads.return_value = []
    store.add_file_host_upload.return_value = 2

    worker = FileHostWorker("testhost", store)

    emitted = []
    worker.upload_progress.connect(
        lambda db_id, host, uploaded, total, speed, path: emitted.append(uploaded)
    )

    _run_two_part_upload(worker, gallery, parts, host_config)

    # One zero-progress emit per part, so a consumer's carried-over byte count
    # is cleared before the new part reports anything of its own.
    assert emitted.count(0) == len(parts), (
        f"expected one zero-progress emit per part, got sequence {emitted}"
    )
    # And the very first thing reported for the run is a zero, not part 1's bytes.
    assert emitted[0] == 0
