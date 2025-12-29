"""
Comprehensive pytest test suite for cookie utilities module.

Tests cookie extraction from Firefox and file-based cookie storage
with proper mocking and edge case coverage.
"""

import pytest
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.network.cookies import (
    get_firefox_cookies,
    load_cookies_from_file,
    _firefox_cookie_cache,
    _firefox_cache_time
)


class TestGetFirefoxCookies:
    """Test suite for Firefox cookie extraction."""

    @pytest.fixture
    def mock_firefox_db(self, tmp_path):
        """Create a mock Firefox cookie database."""
        profile_dir = tmp_path / "firefox" / "test.default-release"
        profile_dir.mkdir(parents=True)

        db_path = profile_dir / "cookies.sqlite"
        conn = sqlite3.connect(str(db_path))

        # Create Firefox cookie schema
        conn.execute("""
            CREATE TABLE moz_cookies (
                name TEXT,
                value TEXT,
                host TEXT,
                path TEXT,
                expiry INTEGER,
                isSecure INTEGER
            )
        """)

        # Insert sample cookies
        cookies = [
            ('session_id', 'abc123def456', '.imx.to', '/', 9999999999, 1),
            ('user_token', 'xyz789uvw', 'imx.to', '/user', 9999999999, 1),
            ('preferences', 'theme=dark', '.imx.to', '/', 9999999999, 0),
            ('other_site', 'data', '.example.com', '/', 9999999999, 1)
        ]
        conn.executemany(
            "INSERT INTO moz_cookies VALUES (?, ?, ?, ?, ?, ?)",
            cookies
        )
        conn.commit()
        conn.close()

        return profile_dir, db_path

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear cookie cache before each test."""
        global _firefox_cookie_cache, _firefox_cache_time
        _firefox_cookie_cache.clear()
        _firefox_cache_time = 0
        yield
        _firefox_cookie_cache.clear()
        _firefox_cache_time = 0

    def test_extract_all_cookies_success(self, mock_firefox_db, monkeypatch):
        """Test successful extraction of all imx.to cookies."""
        profile_dir, db_path = mock_firefox_db
        firefox_dir = profile_dir.parent

        # Mock platform detection
        monkeypatch.setattr('src.network.cookies.platform.system', lambda: 'Linux')

        # Mock path expansion to return firefox parent dir
        def mock_expanduser(path):
            if '~' in path:
                return str(firefox_dir.parent)
            return path

        monkeypatch.setattr('src.network.cookies.os.path.expanduser', mock_expanduser)

        # Mock Firefox directory listing
        def mock_listdir(path):
            if 'firefox' in str(path):
                return ['test.default-release']
            return []

        monkeypatch.setattr('src.network.cookies.os.listdir', mock_listdir)

        # Mock exists to return True for firefox dir and db file
        def mock_exists(path):
            return True

        monkeypatch.setattr('src.network.cookies.os.path.exists', mock_exists)

        # Execute
        cookies = get_firefox_cookies(domain="imx.to")

        # Verify
        assert len(cookies) == 3  # Should exclude other_site
        assert 'session_id' in cookies
        assert 'user_token' in cookies
        assert 'preferences' in cookies

        # Verify cookie structure
        session_cookie = cookies['session_id']
        assert session_cookie['value'] == 'abc123def456'
        assert session_cookie['domain'] == '.imx.to'
        assert session_cookie['path'] == '/'
        assert session_cookie['secure'] is True

    def test_extract_specific_cookies_filtered(self, mock_firefox_db, monkeypatch):
        """Test extraction with specific cookie name filter."""
        profile_dir, db_path = mock_firefox_db
        firefox_dir = profile_dir.parent

        monkeypatch.setattr('platform.system', lambda: 'Linux')
        monkeypatch.setattr('os.path.expanduser', lambda x: str(firefox_dir.parent))
        monkeypatch.setattr('os.listdir', lambda x: ['test.default-release'] if 'firefox' in str(x) else [])
        monkeypatch.setattr('os.path.exists', lambda x: True)

        # Execute - request only session_id (must be secure)
        cookies = get_firefox_cookies(domain="imx.to", cookie_names=['session_id'])

        # Verify - only secure cookies matching names returned
        assert len(cookies) == 1
        assert 'session_id' in cookies
        assert cookies['session_id']['value'] == 'abc123def456'

    def test_extract_filters_insecure_when_names_specified(self, mock_firefox_db, monkeypatch):
        """Test that cookie_names filter requires secure cookies."""
        profile_dir, db_path = mock_firefox_db
        firefox_dir = profile_dir.parent

        monkeypatch.setattr('platform.system', lambda: 'Linux')
        monkeypatch.setattr('os.path.expanduser', lambda x: str(firefox_dir.parent))
        monkeypatch.setattr('os.listdir', lambda x: ['test.default-release'] if 'firefox' in str(x) else [])
        monkeypatch.setattr('os.path.exists', lambda x: True)

        # Execute - request preferences (insecure cookie)
        cookies = get_firefox_cookies(domain="imx.to", cookie_names=['preferences'])

        # Verify - insecure cookie excluded
        assert len(cookies) == 0

    def test_cache_mechanism_reduces_database_access(self, mock_firefox_db, monkeypatch):
        """Test that cookie cache prevents repeated database access."""
        profile_dir, db_path = mock_firefox_db
        firefox_dir = profile_dir.parent

        monkeypatch.setattr('platform.system', lambda: 'Linux')
        monkeypatch.setattr('os.path.expanduser', lambda x: str(firefox_dir.parent))
        monkeypatch.setattr('os.listdir', lambda x: ['test.default-release'] if 'firefox' in str(x) else [])
        monkeypatch.setattr('os.path.exists', lambda x: True)

        # Track sqlite3.connect calls
        original_connect = sqlite3.connect
        connect_calls = []

        def tracked_connect(*args, **kwargs):
            connect_calls.append(args[0])
            return original_connect(*args, **kwargs)

        monkeypatch.setattr('sqlite3.connect', tracked_connect)

        # First call - should hit database
        cookies1 = get_firefox_cookies(domain="imx.to")
        assert len(connect_calls) == 1

        # Second call - should use cache
        cookies2 = get_firefox_cookies(domain="imx.to")
        assert len(connect_calls) == 1  # No additional connection

        # Verify same results
        assert cookies1 == cookies2

    def test_cache_expiration_after_ttl(self, mock_firefox_db, monkeypatch):
        """Test that cache expires after TTL duration."""
        profile_dir, db_path = mock_firefox_db
        firefox_dir = profile_dir.parent

        monkeypatch.setattr('platform.system', lambda: 'Linux')
        monkeypatch.setattr('os.path.expanduser', lambda x: str(firefox_dir.parent))
        monkeypatch.setattr('os.listdir', lambda x: ['test.default-release'] if 'firefox' in str(x) else [])
        monkeypatch.setattr('os.path.exists', lambda x: True)

        # Mock time to simulate cache expiration - use actual numeric values
        import src.network.cookies
        mock_times = [1000.0, 1000.0, 1301.0]  # Start, cached access, expired access
        time_index = [0]

        def mock_time_func():
            idx = time_index[0]
            time_index[0] += 1
            return mock_times[min(idx, len(mock_times) - 1)]

        monkeypatch.setattr('src.network.cookies.time.time', mock_time_func)

        # Track database connections
        original_connect = sqlite3.connect
        connect_calls = []

        def tracked_connect(*args, **kwargs):
            connect_calls.append(args[0])
            return original_connect(*args, **kwargs)

        monkeypatch.setattr('sqlite3.connect', tracked_connect)

        # First call
        get_firefox_cookies(domain="imx.to")
        assert len(connect_calls) == 1

        # Second call after TTL expiration
        get_firefox_cookies(domain="imx.to")
        assert len(connect_calls) == 2  # Cache expired, new connection

    def test_firefox_directory_not_found(self, monkeypatch):
        """Test handling when Firefox directory doesn't exist."""
        monkeypatch.setattr('platform.system', lambda: 'Linux')
        monkeypatch.setattr('os.path.exists', lambda x: False)

        cookies = get_firefox_cookies(domain="imx.to")

        assert cookies == {}

    def test_no_firefox_profile_found(self, tmp_path, monkeypatch):
        """Test handling when no Firefox profiles exist."""
        firefox_dir = tmp_path / "firefox"
        firefox_dir.mkdir()

        monkeypatch.setattr('platform.system', lambda: 'Linux')
        monkeypatch.setattr('os.path.expanduser', lambda x: str(tmp_path))
        monkeypatch.setattr('os.path.exists', lambda x: True)
        monkeypatch.setattr('os.listdir', lambda x: [])

        cookies = get_firefox_cookies(domain="imx.to")

        assert cookies == {}

    def test_cookie_database_missing(self, tmp_path, monkeypatch):
        """Test handling when cookies.sqlite doesn't exist."""
        profile_dir = tmp_path / "firefox" / "test.default"
        profile_dir.mkdir(parents=True)

        monkeypatch.setattr('platform.system', lambda: 'Linux')
        monkeypatch.setattr('os.path.expanduser', lambda x: str(tmp_path))

        def mock_exists(path):
            return 'cookies.sqlite' not in str(path)

        monkeypatch.setattr('os.path.exists', mock_exists)
        monkeypatch.setattr('os.listdir', lambda x: ['test.default'] if 'firefox' in str(x) else [])

        cookies = get_firefox_cookies(domain="imx.to")

        assert cookies == {}

    def test_database_locked_timeout(self, mock_firefox_db, monkeypatch):
        """Test handling of locked Firefox database."""
        profile_dir, db_path = mock_firefox_db
        firefox_dir = profile_dir.parent

        monkeypatch.setattr('platform.system', lambda: 'Linux')
        monkeypatch.setattr('os.path.expanduser', lambda x: str(firefox_dir.parent))
        monkeypatch.setattr('os.listdir', lambda x: ['test.default-release'] if 'firefox' in str(x) else [])
        monkeypatch.setattr('os.path.exists', lambda x: True)

        # Mock locked database
        def mock_connect(*args, **kwargs):
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr('sqlite3.connect', mock_connect)

        cookies = get_firefox_cookies(domain="imx.to")

        # Should return empty dict and cache empty result
        assert cookies == {}

    def test_windows_platform_path_detection(self, mock_firefox_db, monkeypatch):
        """Test Firefox path detection on Windows."""
        profile_dir, db_path = mock_firefox_db

        monkeypatch.setattr('platform.system', lambda: 'Windows')
        monkeypatch.setenv('APPDATA', str(profile_dir.parent.parent))
        monkeypatch.setattr('os.listdir', lambda x: ['test.default-release'] if 'firefox' in str(x).lower() else [])
        monkeypatch.setattr('os.path.exists', lambda x: True)

        cookies = get_firefox_cookies(domain="imx.to")

        assert len(cookies) == 3

    def test_multiple_cache_keys_for_different_filters(self, mock_firefox_db, monkeypatch):
        """Test that different cookie filters create separate cache entries."""
        profile_dir, db_path = mock_firefox_db
        firefox_dir = profile_dir.parent

        monkeypatch.setattr('platform.system', lambda: 'Linux')
        monkeypatch.setattr('os.path.expanduser', lambda x: str(firefox_dir.parent))
        monkeypatch.setattr('os.listdir', lambda x: ['test.default-release'] if 'firefox' in str(x) else [])
        monkeypatch.setattr('os.path.exists', lambda x: True)

        # Get all cookies
        all_cookies = get_firefox_cookies(domain="imx.to")
        assert len(all_cookies) == 3

        # Get filtered cookies
        filtered_cookies = get_firefox_cookies(domain="imx.to", cookie_names=['session_id'])
        assert len(filtered_cookies) == 1

        # Verify cache has separate entries
        assert 'imx.to_all' in _firefox_cookie_cache
        assert 'imx.to_session_id' in _firefox_cookie_cache

    def test_corrupted_database_error_handling(self, tmp_path, monkeypatch):
        """Test handling of corrupted Firefox cookie database."""
        profile_dir = tmp_path / "firefox" / "test.default"
        profile_dir.mkdir(parents=True)

        # Create corrupted database file
        db_path = profile_dir / "cookies.sqlite"
        db_path.write_text("CORRUPTED DATA")

        monkeypatch.setattr('platform.system', lambda: 'Linux')
        monkeypatch.setattr('os.path.expanduser', lambda x: str(tmp_path))
        monkeypatch.setattr('os.listdir', lambda x: ['test.default'] if 'firefox' in str(x) else [])
        monkeypatch.setattr('os.path.exists', lambda x: True)

        cookies = get_firefox_cookies(domain="imx.to")

        # Should handle error gracefully
        assert cookies == {}


class TestLoadCookiesFromFile:
    """Test suite for file-based cookie loading."""

    def test_load_netscape_format_cookies_success(self, tmp_path):
        """Test loading cookies from Netscape format file."""
        cookie_file = tmp_path / "cookies.txt"
        cookie_content = """# Netscape HTTP Cookie File
# This is a generated file!  Do not edit.

.imx.to	TRUE	/	TRUE	9999999999	session_id	abc123def456
imx.to	FALSE	/user	FALSE	9999999999	user_token	xyz789
.imx.to	TRUE	/	TRUE	9999999999	preferences	theme=dark
"""
        cookie_file.write_text(cookie_content)

        cookies = load_cookies_from_file(str(cookie_file))

        assert len(cookies) == 3
        assert cookies['session_id']['value'] == 'abc123def456'
        assert cookies['session_id']['domain'] == '.imx.to'
        assert cookies['session_id']['path'] == '/'
        assert cookies['session_id']['secure'] is True

        assert cookies['user_token']['secure'] is False

    def test_load_ignores_comments_and_empty_lines(self, tmp_path):
        """Test that comments and empty lines are ignored."""
        cookie_file = tmp_path / "cookies.txt"
        cookie_content = """# Comment line

# Another comment
.imx.to	TRUE	/	TRUE	9999999999	session_id	abc123

# More comments
"""
        cookie_file.write_text(cookie_content)

        cookies = load_cookies_from_file(str(cookie_file))

        assert len(cookies) == 1
        assert 'session_id' in cookies

    def test_load_filters_non_imx_cookies(self, tmp_path):
        """Test that only imx.to cookies are loaded."""
        cookie_file = tmp_path / "cookies.txt"
        cookie_content = """.imx.to	TRUE	/	TRUE	9999999999	session_id	abc123
.example.com	TRUE	/	TRUE	9999999999	other_cookie	xyz789
.imx.to	TRUE	/	TRUE	9999999999	user_token	def456
"""
        cookie_file.write_text(cookie_content)

        cookies = load_cookies_from_file(str(cookie_file))

        assert len(cookies) == 2
        assert 'session_id' in cookies
        assert 'user_token' in cookies
        assert 'other_cookie' not in cookies

    def test_load_handles_malformed_lines(self, tmp_path):
        """Test handling of malformed cookie lines."""
        cookie_file = tmp_path / "cookies.txt"
        cookie_content = """.imx.to	TRUE	/	TRUE	9999999999	valid_cookie	value123
malformed line without tabs
.imx.to	INCOMPLETE_LINE
.imx.to	TRUE	/	TRUE	9999999999	another_valid	value456
"""
        cookie_file.write_text(cookie_content)

        cookies = load_cookies_from_file(str(cookie_file))

        # Should load only valid lines
        assert len(cookies) == 2
        assert 'valid_cookie' in cookies
        assert 'another_valid' in cookies

    def test_load_file_not_found(self, tmp_path):
        """Test handling when cookie file doesn't exist."""
        non_existent = tmp_path / "missing_cookies.txt"

        cookies = load_cookies_from_file(str(non_existent))

        assert cookies == {}

    def test_load_empty_file(self, tmp_path):
        """Test loading from empty cookie file."""
        cookie_file = tmp_path / "empty_cookies.txt"
        cookie_file.write_text("")

        cookies = load_cookies_from_file(str(cookie_file))

        assert cookies == {}

    def test_load_file_with_only_comments(self, tmp_path):
        """Test loading from file containing only comments."""
        cookie_file = tmp_path / "comments_only.txt"
        cookie_content = """# Netscape HTTP Cookie File
# Comment 1
# Comment 2
"""
        cookie_file.write_text(cookie_content)

        cookies = load_cookies_from_file(str(cookie_file))

        assert cookies == {}

    def test_load_handles_unicode_in_cookies(self, tmp_path):
        """Test handling of unicode characters in cookie values."""
        cookie_file = tmp_path / "unicode_cookies.txt"
        cookie_content = """.imx.to	TRUE	/	TRUE	9999999999	user_name	José_García
.imx.to	TRUE	/	TRUE	9999999999	preferences	theme=日本語
"""
        cookie_file.write_text(cookie_content, encoding='utf-8')

        cookies = load_cookies_from_file(str(cookie_file))

        assert len(cookies) == 2
        assert 'user_name' in cookies
        assert 'preferences' in cookies

    def test_load_handles_read_permission_error(self, tmp_path, monkeypatch):
        """Test handling of file read permission errors."""
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text(".imx.to	TRUE	/	TRUE	9999999999	test	value")

        # Mock file open to raise permission error
        def mock_open(*args, **kwargs):
            raise PermissionError("Permission denied")

        monkeypatch.setattr('builtins.open', mock_open)

        cookies = load_cookies_from_file(str(cookie_file))

        assert cookies == {}

    def test_load_preserves_cookie_order(self, tmp_path):
        """Test that cookie loading preserves insertion order."""
        cookie_file = tmp_path / "cookies.txt"
        cookie_content = """.imx.to	TRUE	/	TRUE	9999999999	cookie_a	value_a
.imx.to	TRUE	/	TRUE	9999999999	cookie_b	value_b
.imx.to	TRUE	/	TRUE	9999999999	cookie_c	value_c
"""
        cookie_file.write_text(cookie_content)

        cookies = load_cookies_from_file(str(cookie_file))

        # Dict should preserve insertion order (Python 3.7+)
        cookie_names = list(cookies.keys())
        assert cookie_names == ['cookie_a', 'cookie_b', 'cookie_c']

    def test_load_handles_extra_fields(self, tmp_path):
        """Test loading cookies with extra tab-separated fields."""
        cookie_file = tmp_path / "cookies.txt"
        # Standard has 7 fields, this has 8
        cookie_content = ".imx.to	TRUE	/	TRUE	9999999999	session_id	abc123	extra_field\n"
        cookie_file.write_text(cookie_content)

        cookies = load_cookies_from_file(str(cookie_file))

        # Should still load the cookie using first 7 fields
        assert len(cookies) == 1
        assert cookies['session_id']['value'] == 'abc123'

    def test_load_handles_insufficient_fields(self, tmp_path):
        """Test handling of lines with insufficient fields."""
        cookie_file = tmp_path / "cookies.txt"
        cookie_content = """.imx.to	TRUE	/	TRUE	9999999999	incomplete
.imx.to	TRUE	/	TRUE	9999999999	complete	value123
"""
        cookie_file.write_text(cookie_content)

        cookies = load_cookies_from_file(str(cookie_file))

        # Should only load complete cookie
        assert len(cookies) == 1
        assert 'complete' in cookies
        assert 'incomplete' not in cookies
