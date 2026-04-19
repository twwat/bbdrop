"""
File host configuration system for multi-host uploads.

Loads host configurations from JSON files in:
- Built-in: assets/hosts/ (shipped with bbdrop)
- Built-in logos: assets/hosts/logo/ (host logo images)
- Custom: ~/.bbdrop/hosts/ (user-created configs)
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from threading import Lock

from src.utils.paths import get_central_store_base_path
from src.utils.logger import log
from src.core.constants import HOST_FAMILY_PRIORITY


# Module-level locks for thread safety
_config_manager_lock = Lock()  # Protects singleton initialization of _config_manager
_ini_file_lock = Lock()  # Protects INI file read/write operations to prevent race conditions


@dataclass
class HostConfig:
    """Configuration for a file hosting service."""

    # Basic info
    name: str
    icon: Optional[str] = None
    referral_url: Optional[str] = None  # Referral link for the host
    requires_auth: bool = False
    auth_type: Optional[str] = None  # "bearer", "basic", "session", "token_login"

    # Upload configuration
    get_server: Optional[str] = None  # URL to get upload server
    server_response_path: Optional[List[Union[str, int]]] = None  # JSON path to server URL in response
    server_session_id_path: Optional[List[Union[str, int]]] = None  # JSON path to single-use sess_id in get_server response (Katfile-style)
    upload_endpoint: str = ""
    method: str = "POST"  # "POST" or "PUT"
    file_field: str = "file"
    extra_fields: Dict[str, str] = field(default_factory=dict)

    # Response parsing
    response_type: str = "json"  # "json", "text", "regex", "redirect"
    link_path: Optional[List[Union[str, int]]] = None  # JSON path to download link
    link_prefix: str = ""
    link_suffix: str = ""
    link_regex: Optional[str] = None
    file_id_path: Optional[List[Union[str, int]]] = None  # JSON path to file ID (for deletion, tracking)

    # Authentication (session-based)
    login_url: Optional[str] = None
    login_fields: Dict[str, str] = field(default_factory=dict)
    session_id_regex: Optional[str] = None
    upload_page_url: Optional[str] = None  # Page to visit before upload to extract session ID
    session_cookie_name: Optional[str] = None  # Cookie name to use as sess_id (e.g., "xfss" for FileSpace)
    captcha_regex: Optional[str] = None  # Regex to extract captcha code from HTML
    captcha_field: str = "code"  # Field name for captcha submission
    captcha_transform: Optional[str] = None  # Transformation: "move_3rd_to_front", "reverse", etc.

    # Authentication (token-based)
    token_path: Optional[List[Union[str, int]]] = None  # JSON path to token

    # Multi-step upload (like RapidGator)
    upload_init_url: Optional[str] = None
    upload_init_params: List[str] = field(default_factory=list)
    upload_url_path: Optional[List[Union[str, int]]] = None
    upload_id_path: Optional[List[Union[str, int]]] = None
    upload_poll_url: Optional[str] = None
    upload_poll_delay: float = 1.0
    upload_poll_retries: int = 10
    require_file_hash: bool = False
    dedupe_endpoint: Optional[str] = None  # API endpoint for hash-based dedup (e.g., "createFileByHash")

    # K2S-specific multi-step enhancements
    init_method: str = "GET"  # "GET" or "POST"
    init_body_json: bool = False  # Send JSON POST body instead of query params
    file_field_path: Optional[List[Union[str, int]]] = None  # Path to dynamic file field name
    form_data_path: Optional[List[Union[str, int]]] = None  # Path to form_data dict (ajax, params, signature)

    # Default values for INI initialization (NOT runtime values - read from INI)
    # These are copied to INI on first launch, then always read from INI
    defaults: Dict[str, Any] = field(default_factory=dict)

    # Delete functionality
    delete_url: Optional[str] = None  # URL to delete files (e.g., with {file_id} and {token} placeholders)
    delete_method: str = "GET"  # HTTP method for delete
    delete_params: List[str] = field(default_factory=list)  # Required parameters

    # User info / storage monitoring
    user_info_url: Optional[str] = None  # URL to get user info (storage, premium status, etc.)
    storage_total_path: Optional[List[Union[str, int]]] = None  # JSON path to total storage
    storage_used_path: Optional[List[Union[str, int]]] = None  # JSON path to used storage
    storage_left_path: Optional[List[Union[str, int]]] = None  # JSON path to remaining storage
    storage_regex: Optional[str] = None  # Regex to extract storage from HTML (for non-JSON responses)
    premium_status_path: Optional[List[Union[str, int]]] = None  # JSON path to premium status

    # K2S-specific user info enhancements
    user_info_method: str = "GET"  # "GET" or "POST"
    user_info_body_json: bool = False  # Send JSON POST body
    account_expires_path: Optional[List[Union[str, int]]] = None  # JSON path to account expiration timestamp

    # K2S-specific delete enhancements
    delete_body_json: bool = False  # Send JSON POST body for delete

    # Token caching
    token_ttl: Optional[int] = None  # Token time-to-live in seconds (None = no expiration)

    # Session token lifecycle management
    session_token_ttl: Optional[int] = None  # Sess_id TTL in seconds (for proactive refresh)
    stale_token_patterns: List[str] = field(default_factory=list)  # Regex patterns to detect stale tokens
    check_body_on_success: bool = False  # Check response body for stale patterns even on HTTP 200/204

    # Upload timeout configuration
    inactivity_timeout: int = 300  # Seconds of no progress before abort (default 5 minutes)
    upload_timeout: Optional[int] = None  # Total time limit in seconds (None = unlimited)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HostConfig':
        """Create HostConfig from dictionary (loaded from JSON)."""

        # Extract nested structures with defaults
        upload_config = data.get('upload', {})
        response_config = data.get('response', {})
        defaults_config = data.get('defaults', {})  # New unified defaults section
        auth_config = data.get('auth', {})
        multistep_config = data.get('multistep', {})

        return cls(
            # Basic info
            name=data.get('name', ''),
            icon=data.get('icon'),
            referral_url=data.get('referral_url'),
            requires_auth=data.get('requires_auth', False),
            auth_type=data.get('auth_type'),

            # Upload config
            get_server=upload_config.get('get_server'),
            server_response_path=upload_config.get('server_response_path'),
            server_session_id_path=upload_config.get('server_session_id_path'),
            upload_endpoint=upload_config.get('endpoint', ''),
            method=upload_config.get('method', 'POST'),
            file_field=upload_config.get('file_field', 'file'),
            extra_fields=upload_config.get('extra_fields', {}),

            # Response parsing
            response_type=response_config.get('type', 'json'),
            link_path=response_config.get('link_path'),
            link_prefix=response_config.get('link_prefix', ''),
            link_suffix=response_config.get('link_suffix', ''),
            link_regex=response_config.get('link_regex'),
            file_id_path=response_config.get('file_id_path'),

            # Session-based auth
            login_url=auth_config.get('login_url'),
            login_fields=auth_config.get('login_fields', {}),
            session_id_regex=auth_config.get('session_id_regex'),
            upload_page_url=auth_config.get('upload_page_url'),
            session_cookie_name=auth_config.get('session_cookie_name'),
            captcha_regex=auth_config.get('captcha_regex'),
            captcha_field=auth_config.get('captcha_field', 'code'),
            captcha_transform=auth_config.get('captcha_transform'),

            # Token-based auth
            token_path=auth_config.get('token_path'),

            # Multi-step upload
            upload_init_url=multistep_config.get('init_url'),
            upload_init_params=multistep_config.get('init_params', []),
            upload_url_path=multistep_config.get('upload_url_path'),
            upload_id_path=multistep_config.get('upload_id_path'),
            upload_poll_url=multistep_config.get('poll_url'),
            upload_poll_delay=multistep_config.get('poll_delay', 1.0),
            upload_poll_retries=multistep_config.get('poll_retries', 10),
            require_file_hash=multistep_config.get('require_hash', False),
            dedupe_endpoint=multistep_config.get('dedupe_endpoint'),

            # K2S-specific multi-step enhancements
            init_method=multistep_config.get('init_method', 'GET'),
            init_body_json=multistep_config.get('init_body_json', False),
            file_field_path=multistep_config.get('file_field_path'),
            form_data_path=multistep_config.get('form_data_path'),

            # Default values (for INI initialization only)
            defaults=defaults_config,

            # Delete functionality
            delete_url=data.get('delete', {}).get('url'),
            delete_method=data.get('delete', {}).get('method', 'GET'),
            delete_params=data.get('delete', {}).get('params', []),

            # User info / storage
            user_info_url=data.get('user_info', {}).get('url'),
            storage_total_path=data.get('user_info', {}).get('storage_total_path'),
            storage_used_path=data.get('user_info', {}).get('storage_used_path'),
            storage_left_path=data.get('user_info', {}).get('storage_left_path'),
            storage_regex=data.get('user_info', {}).get('storage_regex'),
            premium_status_path=data.get('user_info', {}).get('premium_status_path'),

            # K2S-specific user info enhancements
            user_info_method=data.get('user_info', {}).get('method', 'GET'),
            user_info_body_json=data.get('user_info', {}).get('body_json', False),
            account_expires_path=data.get('user_info', {}).get('account_expires_path'),

            # K2S-specific delete enhancements
            delete_body_json=data.get('delete', {}).get('body_json', False),

            # Token caching
            token_ttl=auth_config.get('token_ttl'),

            # Session token lifecycle
            session_token_ttl=auth_config.get('session_token_ttl'),
            stale_token_patterns=auth_config.get('stale_token_patterns', []),
            check_body_on_success=auth_config.get('check_body_on_success', False),

            # Upload timeout configuration
            inactivity_timeout=upload_config.get('inactivity_timeout', 300),
            upload_timeout=upload_config.get('upload_timeout'),
        )


# ============================================================================
# SIMPLE CONFIG FUNCTIONS - Use these everywhere
# ============================================================================

# Hardcoded default values (used as final fallback)
_HARDCODED_DEFAULTS = {
    "max_connections": 2,
    "max_file_size_mb": None,
    "auto_retry": True,
    "max_retries": 3,
    "inactivity_timeout": 300,
    "upload_timeout": None,
    "bbcode_format": "",
    "spinup_retry_enabled": True,
    "spinup_retry_max_time": 1800,  # 30 minutes in seconds
    "connect_timeout": 30,
}


def get_file_host_setting(host_id: str, key: str, value_type: str = "str") -> Any:
    """Get a file host setting. Simple: INI → JSON default → hardcoded default.

    Special handling for user preferences:
    - 'enabled': Defaults to False if not in INI (hosts disabled by default)
    - 'trigger': Defaults to 'disabled' if not in INI

    Args:
        host_id: Host identifier (e.g., 'filedot')
        key: Setting name (e.g., 'enabled', 'trigger', 'max_connections')
        value_type: 'str', 'bool', or 'int'

    Returns:
        Setting value from INI (if set), else JSON default, else hardcoded default
    """
    from src.utils.paths import get_config_path
    import configparser

    # 1. Check INI first (user override)
    ini_path = get_config_path()
    if os.path.exists(ini_path):
        with _ini_file_lock:  # Thread-safe INI access
            cfg = configparser.ConfigParser()
            cfg.read(ini_path, encoding='utf-8')
            if cfg.has_section("FILE_HOSTS"):
                ini_key = f"{host_id}_{key}"
                if cfg.has_option("FILE_HOSTS", ini_key):
                    try:
                        raw_value = cfg.get("FILE_HOSTS", ini_key)
                        # Skip empty values - treat as "not set" and use defaults
                        if not raw_value or raw_value.strip() == "":
                            # Fall through to default value logic below
                            pass
                        elif value_type == "bool":
                            return cfg.getboolean("FILE_HOSTS", ini_key)
                        elif value_type == "int":
                            return cfg.getint("FILE_HOSTS", ini_key)
                        else:
                            return raw_value
                    except (ValueError, TypeError, configparser.Error) as e:
                        log(f"Invalid value for {ini_key} in INI file: {e}. Using default.",
                            level="warning", category="file_hosts")
                        # Fall through to default value logic below

    # 2. User preferences (not in INI = disabled)
    if key == "enabled":
        return False
    if key == "trigger":
        return "disabled"

    # 3. Host config defaults from JSON
    config_manager = get_config_manager()
    host = config_manager.hosts.get(host_id)
    if host and host.defaults and key in host.defaults:
        return host.defaults[key]

    # 4. Hardcoded fallback
    if key in _HARDCODED_DEFAULTS:
        return _HARDCODED_DEFAULTS[key]
    else:
        log(f"Unknown file host setting requested: {key} for {host_id}",
            level="warning", category="file_hosts")
        return None


def save_file_host_setting(host_id: str, key: str, value: Any) -> None:
    """Save a file host setting to INI. Simple: just write it.

    Args:
        host_id: Host identifier (e.g., 'filedot')
        key: Setting name (e.g., 'enabled', 'trigger')
        value: Value to save

    Raises:
        ValueError: If host_id doesn't exist or key is invalid
    """
    from src.utils.paths import get_config_path
    import configparser

    # Validate host exists
    config_manager = get_config_manager()
    if host_id not in config_manager.hosts:
        raise ValueError(f"Unknown host ID: {host_id}")

    # Validate key (whitelist approach)
    valid_keys = {"enabled", "trigger", "max_connections", "max_file_size_mb",
                  "auto_retry", "max_retries", "inactivity_timeout", "upload_timeout",
                  "bbcode_format", "spinup_retry_enabled", "spinup_retry_max_time",
                  "connect_timeout"}
    if key not in valid_keys:
        raise ValueError(f"Invalid setting key: {key}")

    # Validate value based on key type
    if key == "enabled":
        if not isinstance(value, bool):
            raise ValueError(f"enabled must be bool, got {type(value).__name__}")
    elif key == "trigger":
        valid_triggers = {"disabled", "on_added", "on_started", "on_completed"}
        if value not in valid_triggers:
            raise ValueError(f"trigger must be one of {valid_triggers}, got {value}")
    elif key in {"max_connections", "max_retries"}:
        # Reject booleans explicitly (bool is subclass of int in Python)
        if isinstance(value, bool):
            raise ValueError(f"{key} must be int, not bool")
        if not isinstance(value, int) or value < 1 or value > 100:
            raise ValueError(f"{key} must be int between 1-100, got {value}")
    elif key == "inactivity_timeout":
        # Reject booleans explicitly (bool is subclass of int in Python)
        if isinstance(value, bool):
            raise ValueError(f"{key} must be int, not bool")
        if not isinstance(value, int) or value < 30 or value > 3600:
            raise ValueError(f"{key} must be int between 30-3600, got {value}")
    elif key == "connect_timeout":
        if isinstance(value, bool):
            raise ValueError(f"{key} must be int, not bool")
        if not isinstance(value, int) or value < 10 or value > 180:
            raise ValueError(f"{key} must be int between 10-180, got {value}")
    elif key in {"max_file_size_mb", "upload_timeout"}:
        # Reject booleans explicitly (bool is subclass of int in Python)
        if isinstance(value, bool):
            raise ValueError(f"{key} must be number, not bool")
        if value is not None and (not isinstance(value, (int, float)) or value <= 0):
            raise ValueError(f"{key} must be positive number or None, got {value}")
    elif key == "auto_retry":
        if not isinstance(value, bool):
            raise ValueError(f"auto_retry must be bool, got {type(value).__name__}")
    elif key == "bbcode_format":
        if value is not None and not isinstance(value, str):
            raise ValueError(f"bbcode_format must be str or None, got {type(value).__name__}")
    elif key == "spinup_retry_enabled":
        if not isinstance(value, bool):
            raise ValueError(f"spinup_retry_enabled must be bool, got {type(value).__name__}")
    elif key == "spinup_retry_max_time":
        if isinstance(value, bool):
            raise ValueError(f"{key} must be int, not bool")
        if not isinstance(value, int) or value < 60 or value > 7200:
            raise ValueError(f"{key} must be int between 60-7200, got {value}")

    # Thread-safe read-modify-write operation
    with _ini_file_lock:
        ini_path = get_config_path()  # Get path inside lock to prevent race condition
        cfg = configparser.ConfigParser()

        # Load existing INI
        if os.path.exists(ini_path):
            cfg.read(ini_path, encoding='utf-8')

        # Ensure section exists
        if not cfg.has_section("FILE_HOSTS"):
            cfg.add_section("FILE_HOSTS")

        # Write value
        if value is None:
            # Don't write None to INI - let get_file_host_setting() use defaults
            # Remove key if it exists to clean up INI file
            if cfg.has_option("FILE_HOSTS", f"{host_id}_{key}"):
                cfg.remove_option("FILE_HOSTS", f"{host_id}_{key}")
        else:
            cfg.set("FILE_HOSTS", f"{host_id}_{key}", str(value))

        # Save to file
        try:
            with open(ini_path, 'w', encoding='utf-8') as f:
                cfg.write(f)
            log(f"Saved {host_id}_{key}={value} to INI", level="debug", category="file_hosts")
        except Exception as e:
            log(f"Error saving setting {key} for {host_id}: {e}",
                level="error", category="file_hosts")
            raise


class FileHostConfigManager:
    """Manages loading and accessing file host configurations."""

    def __init__(self):
        self.hosts: Dict[str, HostConfig] = {}
        self.builtin_dir = self._get_builtin_hosts_dir()
        self.custom_dir = self._get_custom_hosts_dir()

    def _get_builtin_hosts_dir(self) -> Path:
        """Get path to built-in host configs (shipped with bbdrop)."""
        # Use centralized get_project_root() for consistency with icon loading
        from src.utils.paths import get_project_root
        project_root = get_project_root()
        hosts_dir = Path(project_root) / "assets" / "hosts"
        return hosts_dir

    def _get_custom_hosts_dir(self) -> Path:
        """Get path to user custom host configs."""
        base_dir = get_central_store_base_path()
        hosts_dir = Path(base_dir) / "hosts"
        hosts_dir.mkdir(parents=True, exist_ok=True)
        return hosts_dir

    def load_all_hosts(self) -> None:
        """Load all host configurations from built-in and custom directories."""
        self.hosts.clear()

        # Load built-in hosts first
        if self.builtin_dir.exists():
            self._load_hosts_from_dir(self.builtin_dir, is_builtin=True)
        else:
            log(f"Built-in hosts directory does not exist: {self.builtin_dir}", level="warning", category="file_hosts")

        # Load custom hosts (can override built-in)
        if self.custom_dir.exists():
            self._load_hosts_from_dir(self.custom_dir, is_builtin=False)

    def reload_hosts(self) -> None:
        """Reload all host configurations (useful for testing or after config changes)."""
        self.load_all_hosts()

    def _load_hosts_from_dir(self, directory: Path, is_builtin: bool) -> None:
        """Load host configs from a directory."""
        if not directory.exists():
            return

        for json_file in directory.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Validate JSON structure
                if not isinstance(data, dict):
                    raise ValueError(f"Config must be a dictionary, got {type(data)}")
                if 'name' not in data:
                    raise ValueError("Config missing required field: 'name'")

                host_config = HostConfig.from_dict(data)
                host_id = json_file.stem  # filename without .json

                self.hosts[host_id] = host_config

                # Config loading is internal - no need to log each file

            except Exception as e:
                log(f"Error loading host config {json_file}: {e}", level="error")

    def get_host(self, host_id: str) -> Optional[HostConfig]:
        """Get a host configuration by ID."""
        return self.hosts.get(host_id)

    def get_enabled_hosts(self) -> Dict[str, HostConfig]:
        """Get all enabled host configurations."""
        result = {}
        for host_id, host_config in self.hosts.items():
            if get_file_host_setting(host_id, "enabled", "bool"):
                result[host_id] = host_config
        return result

    def get_hosts_by_trigger(self, trigger: str) -> Dict[str, HostConfig]:
        """Get hosts that should trigger on a specific event.

        Args:
            trigger: 'added', 'started', or 'completed' (without 'on_' prefix)

        Returns:
            Dictionary of host_id -> HostConfig that match the trigger
        """
        result = {}
        # Normalize trigger to expected format
        expected_trigger = f"on_{trigger}"

        for host_id, host_config in self.hosts.items():
            # Check if enabled
            if not get_file_host_setting(host_id, "enabled", "bool"):
                continue

            # Check trigger mode
            trigger_mode = get_file_host_setting(host_id, "trigger", "str")

            # Match trigger event
            if trigger_mode == expected_trigger:
                result[host_id] = host_config

        return result

    def get_all_host_ids(self) -> List[str]:
        """Get list of all host IDs."""
        return list(self.hosts.keys())

    def enable_host(self, host_id: str) -> bool:
        """Enable a host."""
        if host_id in self.hosts:
            save_file_host_setting(host_id, "enabled", True)
            return True
        return False

    def disable_host(self, host_id: str) -> bool:
        """Disable a host."""
        if host_id in self.hosts:
            save_file_host_setting(host_id, "enabled", False)
            return True
        return False


# Global instance (singleton pattern with thread-safety)
_config_manager: Optional[FileHostConfigManager] = None


def get_config_manager() -> FileHostConfigManager:
    """Get or create the global FileHostConfigManager instance (thread-safe)."""
    global _config_manager

    # Double-checked locking pattern for thread safety
    if _config_manager is None:
        with _config_manager_lock:
            if _config_manager is None:
                _config_manager = FileHostConfigManager()
                _config_manager.load_all_hosts()
    return _config_manager


def get_host_family(host_id: str) -> Optional[str]:
    """Return the backend_family name for a host, or None if host is not in a family.

    Host families share a single backend file store, so a file uploaded through
    one member is instantly available to the others via createFileByHash.
    """
    for family, members in HOST_FAMILY_PRIORITY.items():
        if host_id in members:
            return family
    return None


def get_family_members(family: str) -> list[str]:
    """Return the priority-ordered list of host_ids in a family (copy, safe to mutate)."""
    return list(HOST_FAMILY_PRIORITY.get(family, []))


def select_primary(family: str, enabled_host_ids: set[str]) -> Optional[str]:
    """Return the highest-priority host in `family` present in `enabled_host_ids`.

    Used by QueueManager at queue-entry time to designate the family's primary
    uploader (who does the full upload) from among the hosts enabled for a gallery.
    Returns None if no family member is enabled or the family is unknown.
    """
    for host_id in HOST_FAMILY_PRIORITY.get(family, []):
        if host_id in enabled_host_ids:
            return host_id
    return None


def is_family_dedup_enabled() -> bool:
    """Return whether the K2S family dedup feature is enabled (default True).

    Reads [FILE_HOSTS] k2s_family_dedup_enabled from the INI. If the key is
    missing or the file does not exist, returns True (opt-out, not opt-in).
    """
    import configparser
    import os
    from src.utils.paths import get_config_path

    config_file = get_config_path()
    if not os.path.exists(config_file):
        return True

    with _ini_file_lock:
        config = configparser.ConfigParser()
        try:
            config.read(config_file, encoding="utf-8")
        except configparser.Error:
            return True
        try:
            return config.getboolean(
                "FILE_HOSTS", "k2s_family_dedup_enabled", fallback=True
            )
        except (ValueError, configparser.Error):
            return True


def set_family_dedup_enabled(enabled: bool) -> None:
    """Write [FILE_HOSTS] k2s_family_dedup_enabled to the INI.

    Args:
        enabled: True to enable family dedup (default behavior), False to disable.
    """
    import configparser
    import os
    from src.utils.paths import get_config_path

    config_file = get_config_path()

    with _ini_file_lock:
        config = configparser.ConfigParser()
        if os.path.exists(config_file):
            try:
                config.read(config_file, encoding="utf-8")
            except configparser.Error:
                pass

        if not config.has_section("FILE_HOSTS"):
            config.add_section("FILE_HOSTS")

        config.set("FILE_HOSTS", "k2s_family_dedup_enabled", str(enabled).lower())

        try:
            with open(config_file, "w", encoding="utf-8") as f:
                config.write(f)
            log(
                f"Saved k2s_family_dedup_enabled={enabled} to INI",
                level="debug",
                category="file_hosts",
            )
        except Exception as e:
            log(
                f"Error saving k2s_family_dedup_enabled: {e}",
                level="error",
                category="file_hosts",
            )
            raise


_k2s_storage_lock = Lock()  # Protects read-modify-write on shared K2S storage counter

_K2S_DEFAULT_TOTAL = 10 * 1024 * 1024 * 1024 * 1024  # 10 TiB (K2S labels this "10 TB" on their site)


def get_k2s_family_storage() -> tuple[int, int]:
    """Return (used_bytes, total_bytes) for the shared K2S family storage.

    Reads from QSettings. Total defaults to 10TB if no user override.
    """
    from PyQt6.QtCore import QSettings
    settings = QSettings("BBDropUploader", "BBDropGUI")
    try:
        used = int(settings.value("K2SFamily/storage_used", 0))
    except (ValueError, TypeError):
        used = 0

    total_override = settings.value("K2SFamily/storage_total", None)
    if total_override is not None:
        try:
            total = int(total_override)
        except (ValueError, TypeError):
            total = _K2S_DEFAULT_TOTAL
    else:
        total = _K2S_DEFAULT_TOTAL
    return used, total


def save_k2s_family_storage(used_bytes: int):
    """Save the used bytes for K2S family storage to QSettings."""
    from PyQt6.QtCore import QSettings
    import time
    settings = QSettings("BBDropUploader", "BBDropGUI")
    settings.setValue("K2SFamily/storage_used", str(used_bytes))
    settings.setValue("K2SFamily/storage_ts", str(int(time.time())))
    settings.sync()


def increment_k2s_family_storage(delta_bytes: int) -> tuple[int, int]:
    """Atomically increment the shared K2S storage counter.

    Thread-safe: acquires lock for read-modify-write.

    Returns:
        (total_bytes, left_bytes) after increment.
    """
    with _k2s_storage_lock:
        used, total = get_k2s_family_storage()
        used += delta_bytes
        save_k2s_family_storage(used)
    return total, total - used


def save_k2s_family_quota(total_bytes: int):
    """Save user-configured total quota for K2S family storage."""
    from PyQt6.QtCore import QSettings
    settings = QSettings("BBDropUploader", "BBDropGUI")
    settings.setValue("K2SFamily/storage_total", str(total_bytes))
    settings.sync()


