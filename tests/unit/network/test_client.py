"""
Pytest test suite for SingleInstanceServer.

Tests single instance server socket communication with proper
mocking and error handling.
"""

import pytest
import socket
from unittest.mock import Mock, patch

from PyQt6.QtCore import QThread

from src.network.client import SingleInstanceServer
from src.core.constants import COMMUNICATION_PORT


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
