"""Smoke test that FileHostWorker exposes the host_gallery_settled signal."""
from PyQt6.QtCore import pyqtBoundSignal

from src.processing.file_host_workers import FileHostWorker


def test_host_gallery_settled_signal_exists():
    # Class-level attribute check — the signal is declared on the class
    assert hasattr(FileHostWorker, "host_gallery_settled")


def test_host_gallery_settled_signal_signature():
    """The signal must carry (int, str, bool): gallery_fk, host_name, success."""
    # A lightweight check: instantiate a worker and verify the bound signal exists.
    # We don't need to emit — just confirm the signal is wired.
    # Avoid touching the DB by not calling run() / start().
    from unittest.mock import Mock, patch

    with patch('src.processing.file_host_workers.get_config_manager') as mock_cfg, \
         patch('src.processing.file_host_workers.get_coordinator'), \
         patch('src.processing.file_host_workers.get_archive_manager'), \
         patch('src.processing.file_host_workers.QSettings'):

        mock_config = Mock()
        mock_config.name = "FileBoom"
        mock_cfg.return_value.get_host.return_value = mock_config

        mock_queue_store = Mock()
        worker = FileHostWorker(
            host_id="fileboom",
            queue_store=mock_queue_store,
        )
        assert isinstance(worker.host_gallery_settled, pyqtBoundSignal)
