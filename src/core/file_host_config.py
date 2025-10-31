"""
File host configuration system for multi-host uploads.

Loads host configurations from JSON files in:
- Built-in: assets/hosts/ (shipped with imxup)
- Custom: ~/.imxup/hosts/ (user-created configs)
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field

from imxup import get_central_store_base_path


@dataclass
class HostConfig:
    """Configuration for a file hosting service."""

    # Basic info
    name: str
    enabled: bool = True
    icon: Optional[str] = None
    requires_auth: bool = False
    auth_type: Optional[str] = None  # "bearer", "basic", "session", "token_login"

    # Upload configuration
    get_server: Optional[str] = None  # URL to get upload server
    server_response_path: Optional[List[Union[str, int]]] = None  # JSON path to server URL in response
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

    # Connection limits
    max_file_size_mb: Optional[int] = None
    max_connections: int = 2

    # Trigger settings (when to upload)
    trigger_on_added: bool = False
    trigger_on_started: bool = False
    trigger_on_completed: bool = False

    # Retry settings
    auto_retry: bool = True
    max_retries: int = 3

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

    # Token caching
    token_ttl: Optional[int] = None  # Token time-to-live in seconds (None = no expiration)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HostConfig':
        """Create HostConfig from dictionary (loaded from JSON)."""

        # Extract nested structures with defaults
        upload_config = data.get('upload', {})
        response_config = data.get('response', {})
        limits_config = data.get('limits', {})
        triggers_config = data.get('triggers', {})
        retry_config = data.get('retry', {})
        auth_config = data.get('auth', {})
        multistep_config = data.get('multistep', {})

        return cls(
            # Basic info
            name=data.get('name', ''),
            enabled=data.get('enabled', True),
            icon=data.get('icon'),
            requires_auth=data.get('requires_auth', False),
            auth_type=data.get('auth_type'),

            # Upload config
            get_server=upload_config.get('get_server'),
            server_response_path=upload_config.get('server_response_path'),
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

            # Limits
            max_file_size_mb=limits_config.get('max_file_size_mb'),
            max_connections=limits_config.get('max_connections', 2),

            # Triggers
            trigger_on_added=triggers_config.get('on_added', False),
            trigger_on_started=triggers_config.get('on_started', False),
            trigger_on_completed=triggers_config.get('on_completed', False),

            # Retry
            auto_retry=retry_config.get('auto_retry', True),
            max_retries=retry_config.get('max_retries', 3),

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

            # Token caching
            token_ttl=auth_config.get('token_ttl'),
        )


class FileHostConfigManager:
    """Manages loading and accessing file host configurations."""

    def __init__(self):
        self.hosts: Dict[str, HostConfig] = {}
        self.builtin_dir = self._get_builtin_hosts_dir()
        self.custom_dir = self._get_custom_hosts_dir()

    def _get_builtin_hosts_dir(self) -> Path:
        """Get path to built-in host configs (shipped with imxup)."""
        # assets/hosts/ relative to the imxup root
        import sys
        if getattr(sys, 'frozen', False):
            # Running as PyInstaller bundle
            base_path = Path(sys._MEIPASS)
        else:
            # Running as script - go up from src/core/ to root
            base_path = Path(__file__).parent.parent.parent

        hosts_dir = base_path / "assets" / "hosts"
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

        # Load custom hosts (can override built-in)
        if self.custom_dir.exists():
            self._load_hosts_from_dir(self.custom_dir, is_builtin=False)

    def _load_hosts_from_dir(self, directory: Path, is_builtin: bool) -> None:
        """Load host configs from a directory."""
        if not directory.exists():
            return

        for json_file in directory.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                host_config = HostConfig.from_dict(data)
                host_id = json_file.stem  # filename without .json

                self.hosts[host_id] = host_config

                source = "built-in" if is_builtin else "custom"
                print(f"Loaded {source} host: {host_config.name} ({host_id})")

            except Exception as e:
                print(f"Error loading host config {json_file}: {e}")

    def get_host(self, host_id: str) -> Optional[HostConfig]:
        """Get a host configuration by ID."""
        return self.hosts.get(host_id)

    def get_enabled_hosts(self) -> Dict[str, HostConfig]:
        """Get all enabled host configurations."""
        return {k: v for k, v in self.hosts.items() if v.enabled}

    def get_hosts_by_trigger(self, trigger: str) -> Dict[str, HostConfig]:
        """Get hosts that should trigger on a specific event.

        Args:
            trigger: 'added', 'started', or 'completed'

        Returns:
            Dictionary of host_id -> HostConfig
        """
        result = {}
        for host_id, config in self.hosts.items():
            if not config.enabled:
                continue

            if trigger == 'added' and config.trigger_on_added:
                result[host_id] = config
            elif trigger == 'started' and config.trigger_on_started:
                result[host_id] = config
            elif trigger == 'completed' and config.trigger_on_completed:
                result[host_id] = config

        return result

    def get_all_host_ids(self) -> List[str]:
        """Get list of all host IDs."""
        return list(self.hosts.keys())

    def enable_host(self, host_id: str) -> bool:
        """Enable a host."""
        if host_id in self.hosts:
            self.hosts[host_id].enabled = True
            return True
        return False

    def disable_host(self, host_id: str) -> bool:
        """Disable a host."""
        if host_id in self.hosts:
            self.hosts[host_id].enabled = False
            return True
        return False


# Global instance (singleton pattern)
_config_manager: Optional[FileHostConfigManager] = None


def get_config_manager() -> FileHostConfigManager:
    """Get or create the global FileHostConfigManager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = FileHostConfigManager()
        _config_manager.load_all_hosts()
    return _config_manager
