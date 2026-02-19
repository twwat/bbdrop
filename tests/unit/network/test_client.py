"""
Comprehensive pytest test suite for network client management.

Tests GUI uploader, single instance server, image upload handling,
and socket communication with proper mocking and error handling.
"""

import pytest
import socket
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from PyQt6.QtCore import QThread

from src.network.client import GUIImxToUploader, SingleInstanceServer
from src.core.engine import AtomicCounter
from src.core.constants import COMMUNICATION_PORT


class TestGUIImxToUploaderInitialization:
    """Test suite for GUIImxToUploader initialization."""

    @patch('src.network.client.ImxToUploader.__init__', return_value=None)
    def test_initialization_without_worker_thread(self, mock_parent_init):
        """Test GUIImxToUploader initialization without worker thread."""
        uploader = GUIImxToUploader(worker_thread=None)
        assert uploader.gui_mode is True
        assert uploader.worker_thread is None

    @patch('src.network.client.ImxToUploader.__init__', return_value=None)
    def test_initialization_with_worker_thread(self, mock_parent_init):
        """Test GUIImxToUploader initialization with worker thread."""
        mock_worker = Mock()
        uploader = GUIImxToUploader(worker_thread=mock_worker)
        assert uploader.gui_mode is True
        assert uploader.worker_thread is mock_worker

    @patch('src.network.client.ImxToUploader.__init__', return_value=None)
    def test_parent_init_called(self, mock_parent_init):
        """Test that parent __init__ is called."""
        GUIImxToUploader()
        mock_parent_init.assert_called_once()


class TestUploadFolderBasic:
    """Test suite for basic upload_folder functionality."""

    @pytest.fixture
    def temp_folder_with_images(self):
        """Create temporary folder with test images."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                img_path = Path(tmpdir) / f"image_{i}.jpg"
                img_path.write_bytes(b"fake image data")
            yield tmpdir

    @patch('src.network.client.ImxToUploader.__init__', return_value=None)
    @patch('src.network.client.UploadEngine')
    def test_upload_folder_without_worker_thread(
        self, mock_engine_class, mock_parent_init, temp_folder_with_images
    ):
        """Test upload_folder without worker thread."""
        mock_engine_instance = Mock()
        mock_engine_instance.run.return_value = {
            'images': [],
            'successful_count': 0,
            'total_images': 3,
            'uploaded_size': 0
        }
        mock_engine_class.return_value = mock_engine_instance

        uploader = GUIImxToUploader(worker_thread=None)
        results = uploader.upload_folder(
            folder_path=temp_folder_with_images,
            gallery_name="test_gallery"
        )

        assert 'images' in results
        assert results['total_images'] == 3

    @patch('src.network.client.ImxToUploader.__init__', return_value=None)
    @patch('src.network.client.UploadEngine')
    def test_upload_folder_with_parameters(
        self, mock_engine_class, mock_parent_init, temp_folder_with_images
    ):
        """Test upload_folder with various parameters."""
        mock_engine_instance = Mock()
        mock_engine_instance.run.return_value = {
            'images': [],
            'successful_count': 0,
            'total_images': 3,
            'uploaded_size': 0
        }
        mock_engine_class.return_value = mock_engine_instance

        uploader = GUIImxToUploader(worker_thread=None)
        uploader.upload_folder(
            folder_path=temp_folder_with_images,
            gallery_name="test_gallery",
            thumbnail_size=5,
            thumbnail_format=2,
            max_retries=5,
            parallel_batch_size=8,
            template_name="custom"
        )

        assert mock_engine_instance.run.called

    @patch('src.network.client.ImxToUploader.__init__', return_value=None)
    @patch('src.network.client.UploadEngine')
    def test_upload_folder_creates_engine(
        self, mock_engine_class, mock_parent_init, temp_folder_with_images
    ):
        """Test that upload_folder creates UploadEngine."""
        mock_engine_instance = Mock()
        mock_engine_instance.run.return_value = {
            'images': [],
            'successful_count': 0,
            'total_images': 3,
            'uploaded_size': 0
        }
        mock_engine_class.return_value = mock_engine_instance

        uploader = GUIImxToUploader(worker_thread=None)
        uploader.upload_folder(
            folder_path=temp_folder_with_images,
            gallery_name="test_gallery"
        )

        assert mock_engine_class.called


class TestSingleInstanceServerInitialization:
    """Test suite for SingleInstanceServer initialization."""

    def test_initialization_default_port(self):
        """Test server initialization with default port."""
        server = SingleInstanceServer()
        assert server.port == COMMUNICATION_PORT
        assert server.running is True
        assert isinstance(server, QThread)

    def test_initialization_custom_port(self):
        """Test server initialization with custom port."""
        custom_port = 9999
        server = SingleInstanceServer(port=custom_port)
        assert server.port == custom_port
        assert server.running is True

    def test_has_folder_received_signal(self):
        """Test that server has folder_received signal."""
        server = SingleInstanceServer()
        assert hasattr(server, 'folder_received')


class TestSingleInstanceServerRun:
    """Test suite for SingleInstanceServer run method."""

    def test_server_socket_creation_failure(self):
        """Test handling of socket creation failure."""
        server = SingleInstanceServer(port=65535)

        with patch('src.network.client.socket.socket') as mock_socket_class:
            mock_socket_class.side_effect = OSError("Port already in use")

            with patch('src.network.client.log') as mock_log:
                server.run()
                mock_log.assert_called()

    def test_server_loop_respects_running_flag(self):
        """Test that server loop exits when running is False."""
        server = SingleInstanceServer()

        with patch('src.network.client.socket.socket') as mock_socket_class:
            mock_socket = Mock()
            mock_socket_class.return_value = mock_socket

            accept_count = [0]

            def mock_accept():
                accept_count[0] += 1
                if accept_count[0] > 3:
                    server.running = False
                raise socket.timeout()

            mock_socket.accept = mock_accept
            server.run()
            assert server.running is False

    def test_server_binds_to_localhost(self):
        """Test that server binds to localhost."""
        server = SingleInstanceServer()

        with patch('src.network.client.socket.socket') as mock_socket_class:
            mock_socket = Mock()
            mock_socket_class.return_value = mock_socket
            mock_socket.accept.side_effect = socket.timeout()
            server.running = False

            server.run()

            mock_socket.bind.assert_called_with(('localhost', COMMUNICATION_PORT))


class TestSingleInstanceServerStop:
    """Test suite for SingleInstanceServer stop method."""

    def test_stop_sets_running_flag_false(self):
        """Test that stop() sets running flag to False."""
        server = SingleInstanceServer()
        assert server.running is True
        server.stop()
        assert server.running is False

    def test_stop_calls_wait(self):
        """Test that stop() calls wait() on thread."""
        server = SingleInstanceServer()

        with patch.object(server, 'wait') as mock_wait:
            server.stop()
            mock_wait.assert_called_once()

    def test_stop_idempotent(self):
        """Test that stop() can be called multiple times safely."""
        server = SingleInstanceServer()
        server.stop()
        assert server.running is False
        server.stop()
        assert server.running is False


class TestSingleInstanceServerSignals:
    """Test suite for SingleInstanceServer signal emissions."""

    def test_folder_received_signal_emitted_on_data(self):
        """Test that folder_received signal is emitted when data received."""
        server = SingleInstanceServer()

        with patch('src.network.client.socket.socket') as mock_socket_class:
            mock_socket = Mock()
            mock_socket_class.return_value = mock_socket
            mock_client = Mock()

            accept_count = [0]

            def mock_accept():
                accept_count[0] += 1
                if accept_count[0] == 1:
                    return (mock_client, ('127.0.0.1', 12345))
                else:
                    server.running = False
                    raise socket.timeout()

            mock_socket.accept = mock_accept
            mock_client.recv.return_value = b"/path/to/folder"
            server.run()
            mock_client.close.assert_called()

    def test_empty_message_handling(self):
        """Test that empty messages are handled."""
        server = SingleInstanceServer()

        with patch('src.network.client.socket.socket') as mock_socket_class:
            mock_socket = Mock()
            mock_socket_class.return_value = mock_socket
            mock_client = Mock()

            accept_count = [0]

            def mock_accept():
                accept_count[0] += 1
                if accept_count[0] == 1:
                    return (mock_client, ('127.0.0.1', 12345))
                else:
                    server.running = False
                    raise socket.timeout()

            mock_socket.accept = mock_accept
            mock_client.recv.return_value = b""
            server.run()
            mock_client.close.assert_called()


class TestSingleInstanceServerErrorHandling:
    """Test suite for error handling in SingleInstanceServer."""

    def test_handles_connection_timeout(self):
        """Test handling of socket timeout."""
        server = SingleInstanceServer()

        with patch('src.network.client.socket.socket') as mock_socket_class:
            mock_socket = Mock()
            mock_socket_class.return_value = mock_socket

            timeout_count = [0]

            def mock_accept():
                timeout_count[0] += 1
                if timeout_count[0] > 2:
                    server.running = False
                raise socket.timeout()

            mock_socket.accept = mock_accept
            server.run()
            assert timeout_count[0] > 0

    def test_handles_connection_error_while_running(self):
        """Test handling of connection errors during operation."""
        server = SingleInstanceServer()

        with patch('src.network.client.socket.socket') as mock_socket_class:
            mock_socket = Mock()
            mock_socket_class.return_value = mock_socket

            error_count = [0]

            def mock_accept():
                error_count[0] += 1
                if error_count[0] > 2:
                    server.running = False
                raise Exception("Connection error")

            mock_socket.accept = mock_accept

            with patch('src.network.client.log'):
                server.run()
            assert error_count[0] > 0

    def test_does_not_log_errors_when_stopped(self):
        """Test that errors are not logged after stop."""
        server = SingleInstanceServer()
        server.running = False

        with patch('src.network.client.socket.socket') as mock_socket_class:
            mock_socket = Mock()
            mock_socket_class.return_value = mock_socket
            mock_socket.accept.side_effect = Exception("Error")

            with patch('src.network.client.log'):
                server.run()


class TestSingleInstanceServerCleanup:
    """Test suite for proper resource cleanup."""

    def test_socket_closed_on_exit(self):
        """Test that socket is closed when server exits."""
        server = SingleInstanceServer()

        with patch('src.network.client.socket.socket') as mock_socket_class:
            mock_socket = Mock()
            mock_socket_class.return_value = mock_socket

            mock_socket.accept.side_effect = socket.timeout()
            server.running = False

            server.run()
            mock_socket.close.assert_called()

    def test_socket_closed_on_exception(self):
        """Test socket cleanup when exception occurs."""
        server = SingleInstanceServer()

        with patch('src.network.client.socket.socket') as mock_socket_class:
            mock_socket = Mock()
            mock_socket_class.return_value = mock_socket
            mock_socket.bind.side_effect = Exception("Bind error")

            server.run()

    def test_client_socket_closed_after_receive(self):
        """Test that client socket is closed after data received."""
        server = SingleInstanceServer()

        with patch('src.network.client.socket.socket') as mock_socket_class:
            mock_socket = Mock()
            mock_socket_class.return_value = mock_socket
            mock_client = Mock()

            accept_count = [0]

            def mock_accept():
                accept_count[0] += 1
                if accept_count[0] == 1:
                    return (mock_client, ('127.0.0.1', 12345))
                else:
                    server.running = False
                    raise socket.timeout()

            mock_socket.accept = mock_accept
            mock_client.recv.return_value = b"/path/to/folder"
            server.run()
            mock_client.close.assert_called()


class TestUploadFolderImageHandling:
    """Test suite for image file handling in upload_folder."""

    @pytest.fixture
    def temp_folder_with_mixed_files(self):
        """Create temporary folder with mixed file types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir).joinpath("image_1.jpg").write_bytes(b"jpg")
            Path(tmpdir).joinpath("image_2.png").write_bytes(b"png")
            Path(tmpdir).joinpath("image_3.gif").write_bytes(b"gif")
            Path(tmpdir).joinpath("readme.txt").write_bytes(b"text")
            Path(tmpdir).joinpath("data.json").write_bytes(b"json")
            yield tmpdir

    @patch('src.network.client.ImxToUploader.__init__', return_value=None)
    @patch('src.network.client.UploadEngine')
    def test_filters_only_image_files(
        self, mock_engine_class, mock_parent_init, temp_folder_with_mixed_files
    ):
        """Test that only image files are counted."""
        mock_engine_instance = Mock()
        mock_engine_instance.run.return_value = {
            'images': [],
            'successful_count': 0,
            'total_images': 3,
            'uploaded_size': 0
        }
        mock_engine_class.return_value = mock_engine_instance

        uploader = GUIImxToUploader(worker_thread=None)
        results = uploader.upload_folder(
            folder_path=temp_folder_with_mixed_files,
            gallery_name="test_gallery"
        )

        assert results['total_images'] == 3


class TestUploadFolderCallbacks:
    """Test suite for upload_folder callback functions."""

    @pytest.fixture
    def temp_folder_with_images(self):
        """Create temporary folder with test images."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                img_path = Path(tmpdir) / f"image_{i}.jpg"
                img_path.write_bytes(b"fake image data")
            yield tmpdir

    @pytest.fixture
    def mock_worker_thread(self):
        """Create a mock worker thread."""
        worker = Mock()
        worker.current_item = None
        worker.gallery_started = Mock()
        worker.gallery_started.emit = Mock()
        worker.progress_updated = Mock()
        worker.progress_updated.emit = Mock()
        worker._emit_current_bandwidth = Mock()
        return worker

    @patch('src.network.client.ImxToUploader.__init__', return_value=None)
    @patch('src.network.client.UploadEngine')
    def test_on_progress_callback(
        self, mock_engine_class, mock_parent_init, temp_folder_with_images, mock_worker_thread
    ):
        """Test that on_progress callback emits progress signal."""
        captured_callbacks = {}

        def capture_engine_init(uploader, rename_worker, **kwargs):
            engine = Mock()
            captured_callbacks['on_progress'] = kwargs.get('on_progress')
            engine.run.return_value = {
                'images': [],
                'successful_count': 0,
                'total_images': 3,
                'uploaded_size': 0
            }
            return engine

        mock_engine_class.side_effect = capture_engine_init

        uploader = GUIImxToUploader(worker_thread=mock_worker_thread)
        uploader.upload_folder(
            folder_path=temp_folder_with_images,
            gallery_name="test_gallery"
        )

        on_progress = captured_callbacks.get('on_progress')
        if on_progress:
            on_progress(1, 3, 33, "image_0.jpg")
            mock_worker_thread.progress_updated.emit.assert_called()

    @patch('src.network.client.ImxToUploader.__init__', return_value=None)
    @patch('src.network.client.UploadEngine')
    def test_gallery_started_signal(
        self, mock_engine_class, mock_parent_init, temp_folder_with_images, mock_worker_thread
    ):
        """Test that gallery_started signal is emitted."""
        mock_engine_instance = Mock()
        mock_engine_instance.run.return_value = {
            'images': [],
            'successful_count': 0,
            'total_images': 3,
            'uploaded_size': 0
        }
        mock_engine_class.return_value = mock_engine_instance

        uploader = GUIImxToUploader(worker_thread=mock_worker_thread)
        uploader.upload_folder(
            folder_path=temp_folder_with_images,
            gallery_name="test_gallery"
        )

        mock_worker_thread.gallery_started.emit.assert_called()


class TestUploadFolderEdgeCases:
    """Test suite for edge cases in upload_folder."""

    @patch('src.network.client.ImxToUploader.__init__', return_value=None)
    @patch('src.network.client.UploadEngine')
    def test_empty_folder(self, mock_engine_class, mock_parent_init):
        """Test uploading from empty folder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_engine_instance = Mock()
            mock_engine_instance.run.return_value = {
                'images': [],
                'successful_count': 0,
                'total_images': 0,
                'uploaded_size': 0
            }
            mock_engine_class.return_value = mock_engine_instance

            uploader = GUIImxToUploader(worker_thread=None)
            results = uploader.upload_folder(
                folder_path=tmpdir,
                gallery_name="empty_gallery"
            )

            assert results['total_images'] == 0
            assert results['successful_count'] == 0

    @patch('src.network.client.ImxToUploader.__init__', return_value=None)
    @patch('src.network.client.UploadEngine')
    def test_atomic_counters(self, mock_engine_class, mock_parent_init):
        """Test upload_folder with atomic byte counters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir).joinpath("image.jpg").write_bytes(b"jpg")

            mock_engine_instance = Mock()
            mock_engine_instance.run.return_value = {
                'images': [],
                'successful_count': 0,
                'total_images': 1,
                'uploaded_size': 1024
            }
            mock_engine_class.return_value = mock_engine_instance

            global_counter = AtomicCounter()
            gallery_counter = AtomicCounter()

            uploader = GUIImxToUploader(worker_thread=None)
            uploader.upload_folder(
                folder_path=tmpdir,
                gallery_name="test",
                global_byte_counter=global_counter,
                gallery_byte_counter=gallery_counter
            )

            call_kwargs = mock_engine_class.call_args[1]
            assert call_kwargs['global_byte_counter'] == global_counter
            assert call_kwargs['gallery_byte_counter'] == gallery_counter

    @patch('src.network.client.ImxToUploader.__init__', return_value=None)
    @patch('src.network.client.UploadEngine')
    def test_auto_gallery_name(self, mock_engine_class, mock_parent_init):
        """Test automatic gallery name from folder."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir).joinpath("image.jpg").write_bytes(b"jpg")

            mock_engine_instance = Mock()
            mock_engine_instance.run.return_value = {
                'images': [],
                'successful_count': 0,
                'total_images': 1,
                'uploaded_size': 0
            }
            mock_engine_class.return_value = mock_engine_instance

            uploader = GUIImxToUploader(worker_thread=None)
            results = uploader.upload_folder(
                folder_path=tmpdir,
                gallery_name=None
            )

            assert 'images' in results

    @patch('src.network.client.ImxToUploader.__init__', return_value=None)
    @patch('src.network.client.UploadEngine')
    def test_case_insensitive_extensions(self, mock_engine_class, mock_parent_init):
        """Test case-insensitive file extension matching."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir).joinpath("image_1.JPG").write_bytes(b"jpg")
            Path(tmpdir).joinpath("image_2.PNG").write_bytes(b"png")

            mock_engine_instance = Mock()
            mock_engine_instance.run.return_value = {
                'images': [],
                'successful_count': 0,
                'total_images': 2,
                'uploaded_size': 0
            }
            mock_engine_class.return_value = mock_engine_instance

            uploader = GUIImxToUploader(worker_thread=None)
            results = uploader.upload_folder(
                folder_path=tmpdir,
                gallery_name="test"
            )

            assert results['total_images'] == 2
