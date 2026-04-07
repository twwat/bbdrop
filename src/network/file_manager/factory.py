"""Factory for creating file manager clients.

Routes host_id to the appropriate FileManagerClient subclass.
Handles credential loading from the OS keyring.
"""

from __future__ import annotations

from typing import Optional

from src.network.file_manager.client import FileManagerClient
from src.network.file_manager.k2s_client import K2S_API_BASES
from src.utils.logger import log

# Host IDs that support file management
K2S_FAMILY = set(K2S_API_BASES.keys())
SESSION_HOSTS = {"filespace", "filedot"}  # session-based auth

SUPPORTED_HOSTS = K2S_FAMILY | {"rapidgator", "katfile", "filespace", "filedot"}


def create_file_manager_client(
    host_id: str,
    auth_token: Optional[str] = None,
    session_cookie: Optional[str] = None,
    sess_id: Optional[str] = None,
) -> FileManagerClient:
    """Create a file manager client for the given host.

    Args:
        host_id: Host identifier (e.g. 'keep2share', 'rapidgator').
        auth_token: Pre-decrypted auth token/API key. If None, loads from keyring.
        session_cookie: Session cookie for session-based hosts (Filespace, Filedot).
        sess_id: CSRF session ID for Filedot.

    Returns:
        A FileManagerClient instance.

    Raises:
        ValueError: If host is unsupported or no credentials available.
    """
    if host_id not in SUPPORTED_HOSTS:
        raise ValueError(f"File manager not supported for host: {host_id}")

    # Load credentials if not provided
    if not auth_token and host_id not in SESSION_HOSTS:
        auth_token = _load_auth_token(host_id)
    if not auth_token and host_id not in SESSION_HOSTS:
        raise ValueError(f"No credentials available for {host_id}")

    if host_id in K2S_FAMILY:
        from src.network.file_manager.k2s_client import K2SFileManagerClient
        return K2SFileManagerClient(host_id=host_id, access_token=auth_token)

    if host_id == "rapidgator":
        from src.network.file_manager.rapidgator_client import RapidgatorFileManagerClient
        return RapidgatorFileManagerClient(token=auth_token)

    if host_id == "katfile":
        from src.network.file_manager.xfs_client import XFSFileManagerClient
        return XFSFileManagerClient(host_id="katfile", api_key=auth_token)

    if host_id == "filespace":
        from src.network.file_manager.filespace_client import FilespaceFileManagerClient
        api_key = auth_token or _load_auth_token(host_id)
        cookie = session_cookie or _load_session_cookie(host_id)
        if not api_key:
            raise ValueError("No API key available for Filespace")
        return FilespaceFileManagerClient(
            api_key=api_key, session_cookie=cookie
        )

    if host_id == "filedot":
        from src.network.file_manager.filedot_client import FiledotFileManagerClient
        cookie = session_cookie or _load_session_cookie(host_id)
        if not cookie:
            raise ValueError("No session cookie available for Filedot")
        sid = sess_id or ""
        return FiledotFileManagerClient(
            session_cookie=cookie, sess_id=sid
        )

    raise ValueError(f"No file manager client for host: {host_id}")


def _load_auth_token(host_id: str) -> Optional[str]:
    """Load and decrypt auth token from OS keyring.

    For K2S-family and Katfile (api_key auth), the decrypted credential IS the token.
    For RapidGator (token_login), tries token cache first, then logs in.
    """
    if host_id == "rapidgator":
        return _load_rapidgator_token()

    try:
        from src.utils.credentials import get_credential, decrypt_password

        encrypted = get_credential(f"file_host_{host_id}_credentials")
        if encrypted:
            return decrypt_password(encrypted)
    except Exception as e:
        log(f"Failed to load credentials for {host_id}: {e}",
            level="warning", category="file_manager")

    return None


def _load_session_cookie(host_id: str) -> Optional[str]:
    """Load session cookie for session-based hosts.

    These hosts use session auth — we try to get the cookie from the
    active FileHostWorker's session state if available.
    """
    try:
        from src.utils.credentials import get_credential, decrypt_password

        encrypted = get_credential(f"file_host_{host_id}_credentials")
        if encrypted:
            return decrypt_password(encrypted)
    except Exception as e:
        log(f"Failed to load session for {host_id}: {e}",
            level="warning", category="file_manager")

    return None


def _load_rapidgator_token() -> Optional[str]:
    """Load RapidGator token — cache first, then login with stored credentials."""
    try:
        from src.network.token_cache import get_token_cache
        cached = get_token_cache().get_token("rapidgator")
        if cached:
            return cached
    except Exception:
        pass

    # Fall back to login
    try:
        from src.utils.credentials import get_credential, decrypt_password
        encrypted = get_credential("file_host_rapidgator_credentials")
        if not encrypted:
            return None

        decrypted = decrypt_password(encrypted)
        if not decrypted:
            return None

        from src.core.file_host_config import get_config_manager
        config_mgr = get_config_manager()
        rg_config = config_mgr.get_host_config("rapidgator")
        if not rg_config:
            return None

        from src.network.file_host_client import FileHostClient
        client = FileHostClient(rg_config, credentials=decrypted, host_id="rapidgator")
        if client.auth_token:
            return client.auth_token
    except Exception as e:
        log(f"Failed to get rapidgator token: {e}",
            level="warning", category="file_manager")

    return None


def get_supported_hosts() -> list[str]:
    """Return list of host IDs that support file management."""
    return sorted(SUPPORTED_HOSTS)


def is_host_supported(host_id: str) -> bool:
    """Check if a host supports file management."""
    return host_id in SUPPORTED_HOSTS
