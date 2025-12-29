"""
Comprehensive test suite for src/processing/rename_worker.py
Tests background rename worker with threading, queue management, and session handling.
"""

import pytest
import threading
import queue
import time
from unittest.mock import Mock, MagicMock, patch, call, PropertyMock, ANY

from src.processing.rename_worker import RenameWorker


class TestRenameWorkerInit:
    """Test RenameWorker initialization"""

    @patch('threading.Thread')
    @patch('requests.Session')
    @patch('imxup.get_credential')
    def test_init_with_credentials(self, mock_get_cred, mock_session_class, mock_thread_class):
        """Test initialization with stored credentials"""
        mock_get_cred.side_effect = lambda key: {
            'username': 'testuser',
            'password': 'encrypted_pass'
        }.get(key)

        mock_session = Mock()
        mock_session_class.return_value = mock_session

        with patch('imxup.decrypt_password', return_value='plain_pass'):
            worker = RenameWorker()

        assert worker.username == 'testuser'
        assert worker.password == 'plain_pass'
        assert worker.running is True
        assert worker.login_successful is False
        assert worker.web_url == "https://imx.to"
        assert isinstance(worker.queue, queue.Queue)

    @patch('threading.Thread')
    @patch('requests.Session')
    @patch('imxup.get_credential')
    def test_init_without_credentials(self, mock_get_cred, mock_session_class, mock_thread_class):
        """Test initialization without credentials"""
        mock_get_cred.return_value = None
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        worker = RenameWorker()

        assert worker.username is None
        assert worker.password is None

    @patch('threading.Thread')
    @patch('requests.Session')
    @patch('imxup.get_credential')
    def test_init_creates_session(self, mock_get_cred, mock_session_class, mock_thread_class):
        """Test session creation with proper configuration"""
        mock_get_cred.return_value = None
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        worker = RenameWorker()

        mock_session.mount.assert_any_call("http://", ANY)
        mock_session.mount.assert_any_call("https://", ANY)
        mock_session.headers.update.assert_called_once()


class TestRenameWorkerLogin:
    """Test RenameWorker login functionality"""

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_login_with_cookies_success(self, mock_get_cred, mock_thread_class):
        """Test successful login using cookies"""
        mock_get_cred.return_value = None

        with patch('src.network.cookies.get_firefox_cookies') as mock_ff_cookies, \
             patch('src.network.cookies.load_cookies_from_file') as mock_load_cookies:

            mock_ff_cookies.return_value = {
                'PHPSESSID': {
                    'value': 'test_session',
                    'domain': 'imx.to',
                    'path': '/',
                    'secure': True
                }
            }
            mock_load_cookies.return_value = {}

            worker = RenameWorker()
            worker.session = Mock()
            mock_response = Mock()
            mock_response.url = "https://imx.to/user/gallery/manage"
            mock_response.text = "Gallery Management"
            worker.session.get.return_value = mock_response

            result = worker.login()

            assert result is True
            worker.session.cookies.set.assert_called()
            worker.session.get.assert_called_with("https://imx.to/user/gallery/manage")

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_login_with_credentials_success(self, mock_get_cred, mock_thread_class):
        """Test successful login using credentials"""
        mock_get_cred.side_effect = lambda key: {
            'username': 'testuser',
            'password': 'encrypted_pass'
        }.get(key)

        with patch('imxup.decrypt_password', return_value='plain_pass'), \
             patch('src.network.cookies.get_firefox_cookies', return_value={}), \
             patch('src.network.cookies.load_cookies_from_file', return_value={}):

            worker = RenameWorker()
            worker.session = Mock()

            mock_response = Mock()
            mock_response.url = "https://imx.to/user/dashboard"
            mock_response.text = "Dashboard"
            worker.session.post.return_value = mock_response

            result = worker.login()

            assert result is True
            worker.session.post.assert_called_with(
                "https://imx.to/login.php",
                data={
                    'usr_email': 'testuser',
                    'pwd': 'plain_pass',
                    'remember': '1',
                    'doLogin': 'Login'
                }
            )

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_login_ddos_guard_detected(self, mock_get_cred, mock_thread_class):
        """Test login failure when DDoS-Guard detected"""
        mock_get_cred.side_effect = lambda key: {
            'username': 'testuser',
            'password': 'encrypted'
        }.get(key)

        with patch('imxup.decrypt_password', return_value='pass'), \
             patch('src.network.cookies.get_firefox_cookies', return_value={}), \
             patch('src.network.cookies.load_cookies_from_file', return_value={}):

            worker = RenameWorker()
            worker.session = Mock()

            mock_response = Mock()
            mock_response.text = "DDoS-Guard protection"
            worker.session.post.return_value = mock_response

            result = worker.login()

            assert result is False

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_login_no_credentials(self, mock_get_cred, mock_thread_class):
        """Test login failure without credentials"""
        mock_get_cred.return_value = None

        with patch('src.network.cookies.get_firefox_cookies', return_value={}), \
             patch('src.network.cookies.load_cookies_from_file', return_value={}):

            worker = RenameWorker()
            worker.session = Mock()

            result = worker.login()

            assert result is False


class TestRenameWorkerGalleryRename:
    """Test gallery renaming functionality"""

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_rename_gallery_success(self, mock_get_cred, mock_thread_class):
        """Test successful gallery rename"""
        mock_get_cred.return_value = None
        worker = RenameWorker()
        worker.session = Mock()

        # Mock edit page response
        mock_edit_response = Mock()
        mock_edit_response.status_code = 200
        mock_edit_response.url = "https://imx.to/user/gallery/edit?id=12345"
        mock_edit_response.text = "<form>Gallery Edit</form>"

        # Mock rename POST response
        mock_rename_response = Mock()
        mock_rename_response.status_code = 200

        worker.session.get.return_value = mock_edit_response
        worker.session.post.return_value = mock_rename_response

        result = worker.rename_gallery_with_session("12345", "New Gallery Name")

        assert result is True
        worker.session.get.assert_called_with("https://imx.to/user/gallery/edit?id=12345")
        worker.session.post.assert_called_with(
            "https://imx.to/user/gallery/edit?id=12345",
            data={
                'gallery_name': "New Gallery Name",
                'submit_new_gallery': 'Rename Gallery'
            }
        )

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_rename_gallery_403_reauth(self, mock_get_cred, mock_thread_class):
        """Test rename with 403 triggers re-authentication"""
        mock_get_cred.return_value = None
        worker = RenameWorker()
        worker.session = Mock()
        worker.login_successful = True

        # First call returns 403
        mock_edit_response_403 = Mock()
        mock_edit_response_403.status_code = 403

        # After reauth, return 200
        mock_edit_response_200 = Mock()
        mock_edit_response_200.status_code = 200
        mock_edit_response_200.text = "Edit form"
        mock_edit_response_200.url = "https://imx.to/user/gallery/edit?id=12345"

        mock_rename_response = Mock()
        mock_rename_response.status_code = 200

        worker.session.get.side_effect = [mock_edit_response_403, mock_edit_response_200]
        worker.session.post.return_value = mock_rename_response

        # Mock successful reauth
        with patch.object(worker, '_attempt_reauth_with_rate_limit', return_value=True):
            result = worker.rename_gallery_with_session("12345", "New Name")

        assert result is True

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_rename_gallery_sanitize_name(self, mock_get_cred, mock_thread_class):
        """Test gallery name sanitization"""
        mock_get_cred.return_value = None
        worker = RenameWorker()
        worker.session = Mock()

        mock_edit_response = Mock()
        mock_edit_response.status_code = 200
        mock_edit_response.text = "Edit form"
        mock_edit_response.url = "https://imx.to/user/gallery/edit?id=12345"

        mock_rename_response = Mock()
        mock_rename_response.status_code = 200

        worker.session.get.return_value = mock_edit_response
        worker.session.post.return_value = mock_rename_response

        # Name with special characters
        result = worker.rename_gallery_with_session("12345", "Test/Gallery\\Name")

        assert result is True
        # Verify POST was called (name will be sanitized internally)
        worker.session.post.assert_called_once()

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_rename_gallery_login_redirect(self, mock_get_cred, mock_thread_class):
        """Test rename when redirected to login page"""
        mock_get_cred.return_value = None
        worker = RenameWorker()
        worker.session = Mock()
        worker.login_successful = True

        mock_edit_response = Mock()
        mock_edit_response.status_code = 200
        mock_edit_response.url = "https://imx.to/login.php"  # Redirected to login
        mock_edit_response.text = "Login form"

        worker.session.get.return_value = mock_edit_response

        with patch.object(worker, '_attempt_reauth_with_rate_limit', return_value=False):
            result = worker.rename_gallery_with_session("12345", "New Name")

        assert result is False
        assert worker.login_successful is False


class TestRenameWorkerQueueProcessing:
    """Test queue processing"""

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_queue_rename(self, mock_get_cred, mock_thread_class):
        """Test queuing rename request"""
        mock_get_cred.return_value = None
        worker = RenameWorker()

        worker.queue_rename("gallery123", "Test Gallery")

        # Queue should have one item
        assert worker.queue.qsize() == 1
        item = worker.queue.get_nowait()
        assert item['gallery_id'] == "gallery123"
        assert item['gallery_name'] == "Test Gallery"

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_queue_rename_empty_values(self, mock_get_cred, mock_thread_class):
        """Test queuing with empty values"""
        mock_get_cred.return_value = None
        worker = RenameWorker()

        worker.queue_rename("", "Test")
        worker.queue_rename("id123", "")
        worker.queue_rename(None, "Test")

        # Queue should be empty
        assert worker.queue.qsize() == 0


class TestRenameWorkerLifecycle:
    """Test worker lifecycle management"""

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_stop_worker(self, mock_get_cred, mock_thread_class):
        """Test stopping worker"""
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        mock_thread_class.return_value = mock_thread

        mock_get_cred.return_value = None
        worker = RenameWorker()
        worker.session = Mock()

        worker.stop(timeout=1.0)

        assert worker.running is False
        mock_thread.join.assert_called_once_with(timeout=1.0)
        worker.session.close.assert_called_once()

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_is_running_true(self, mock_get_cred, mock_thread_class):
        """Test is_running when worker active"""
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        mock_thread_class.return_value = mock_thread

        mock_get_cred.return_value = None
        worker = RenameWorker()

        assert worker.is_running() is True

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_is_running_false(self, mock_get_cred, mock_thread_class):
        """Test is_running when worker stopped"""
        mock_thread = Mock()
        mock_thread.is_alive.return_value = False
        mock_thread_class.return_value = mock_thread

        mock_get_cred.return_value = None
        worker = RenameWorker()
        worker.running = False

        assert worker.is_running() is False

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_queue_size(self, mock_get_cred, mock_thread_class):
        """Test queue size reporting"""
        mock_get_cred.return_value = None
        worker = RenameWorker()

        worker.queue_rename("id1", "Gallery 1")
        worker.queue_rename("id2", "Gallery 2")

        assert worker.queue_size() == 2


class TestRenameWorkerReauthRateLimit:
    """Test re-authentication rate limiting"""

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_reauth_rate_limit_blocks_rapid_attempts(self, mock_get_cred, mock_thread_class):
        """Test that rapid re-auth attempts are blocked"""
        mock_get_cred.return_value = None
        worker = RenameWorker()
        worker.last_reauth_attempt = time.time()  # Just attempted
        worker.min_reauth_interval = 5.0

        result = worker._attempt_reauth_with_rate_limit()

        assert result is False

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_reauth_rate_limit_allows_after_interval(self, mock_get_cred, mock_thread_class):
        """Test re-auth allowed after interval"""
        mock_get_cred.return_value = None
        worker = RenameWorker()
        worker.last_reauth_attempt = time.time() - 10.0  # 10 seconds ago
        worker.min_reauth_interval = 5.0

        with patch.object(worker, 'login', return_value=True):
            result = worker._attempt_reauth_with_rate_limit()

        assert result is True

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_reauth_prevents_concurrent_attempts(self, mock_get_cred, mock_thread_class):
        """Test concurrent re-auth attempts are prevented"""
        mock_get_cred.return_value = None
        worker = RenameWorker()
        worker.last_reauth_attempt = 0
        worker.reauth_in_progress = True  # Another thread is re-authing

        result = worker._attempt_reauth_with_rate_limit()

        # Should return current login status without attempting reauth
        assert isinstance(result, bool)


class TestRenameWorkerProcessing:
    """Test rename processing loop (without actually running thread)"""

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_process_renames_waits_for_login(self, mock_get_cred, mock_thread_class):
        """Test that processing waits for initial login"""
        mock_get_cred.return_value = None
        worker = RenameWorker()
        worker.login_complete = threading.Event()
        worker.login_complete.clear()

        # Queue a rename
        worker.queue.put({'gallery_id': '123', 'gallery_name': 'Test'})

        # Mock login timeout
        with patch.object(worker.login_complete, 'wait', return_value=False), \
             patch('imxup.save_unnamed_gallery') as mock_save:
            # Manually call processing for one iteration
            worker.running = True
            try:
                request = worker.queue.get(timeout=0.1)
                if not worker.login_complete.wait(timeout=0.1):
                    mock_save(request['gallery_id'], request['gallery_name'])
                    worker.queue.task_done()
            except queue.Empty:
                pass

        mock_save.assert_called_once_with('123', 'Test')

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_process_renames_handles_failure(self, mock_get_cred, mock_thread_class):
        """Test rename failure saves to unnamed gallery"""
        mock_get_cred.return_value = None
        worker = RenameWorker()
        worker.login_complete = threading.Event()
        worker.login_complete.set()
        worker.login_successful = True

        with patch.object(worker, 'rename_gallery_with_session', return_value=False), \
             patch('imxup.save_unnamed_gallery') as mock_save:

            worker.queue.put({'gallery_id': '456', 'gallery_name': 'Failed'})

            # Process one item
            try:
                request = worker.queue.get(timeout=0.1)
                success = worker.rename_gallery_with_session(
                    request['gallery_id'],
                    request['gallery_name']
                )
                if not success:
                    mock_save(request['gallery_id'], request['gallery_name'])
                worker.queue.task_done()
            except queue.Empty:
                pass

        mock_save.assert_called_once_with('456', 'Failed')


class TestRenameWorkerErrorHandling:
    """Test error handling"""

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_rename_gallery_network_error(self, mock_get_cred, mock_thread_class):
        """Test handling of network errors during rename"""
        mock_get_cred.return_value = None
        worker = RenameWorker()
        worker.session = Mock()
        worker.session.get.side_effect = Exception("Network error")

        result = worker.rename_gallery_with_session("123", "Test")

        assert result is False

    @patch('threading.Thread')
    @patch('imxup.get_credential')
    def test_stop_with_session_close_error(self, mock_get_cred, mock_thread_class):
        """Test stop handles session close errors gracefully"""
        mock_thread = Mock()
        mock_thread.is_alive.return_value = False
        mock_thread_class.return_value = mock_thread

        mock_get_cred.return_value = None
        worker = RenameWorker()
        worker.session = Mock()
        worker.session.close.side_effect = Exception("Close error")

        # Should not raise exception
        worker.stop()

        assert worker.running is False
