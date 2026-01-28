"""
Image host configuration system for multi-host image uploads.

Loads host configurations from JSON files in:
- Built-in: assets/image_hosts/ (shipped with bbdrop)
- Custom: ~/.bbdrop/image_hosts/ (user-created configs)

Provides 3-tier setting fallback: INI -> JSON defaults -> hardcoded defaults.
"""

import os
import json
import configparser
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from threading import Lock

from src.utils.logger import log


# Module-level locks for thread safety
_config_manager_lock = Lock()
_ini_file_lock = Lock()


@dataclass
class ImageHostConfig:
    """Configuration for an image hosting service."""

    name: str                                        # "IMX.to"
    host_id: str = ""                                # "imx"
    icon: Optional[str] = None                       # "imx.png"
    requires_auth: bool = False
    auth_type: Optional[str] = None                  # "api_key", "session", "api_key_or_session"

    # Gallery
    gallery_url_template: str = ""                   # "https://imx.to/g/{gallery_id}"
    thumbnail_url_template: str = ""                 # "https://imx.to/u/t/{img_id}{ext}"

    # Host-specific thumbnail options (populated from JSON)
    thumbnail_sizes: List[Dict[str, Any]] = field(default_factory=list)
    thumbnail_formats: List[Dict[str, Any]] = field(default_factory=list)

    # Per-host defaults (fallback for settings)
    defaults: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, host_id: str, data: Dict[str, Any]) -> 'ImageHostConfig':
        """Create ImageHostConfig from dictionary (loaded from JSON)."""
        return cls(
            name=data.get('name', ''),
            host_id=host_id,
            icon=data.get('icon'),
            requires_auth=data.get('requires_auth', False),
            auth_type=data.get('auth_type'),
            gallery_url_template=data.get('gallery_url_template', ''),
            thumbnail_url_template=data.get('thumbnail_url_template', ''),
            thumbnail_sizes=data.get('thumbnail_sizes', []),
            thumbnail_formats=data.get('thumbnail_formats', []),
            defaults=data.get('defaults', {}),
        )


# Hardcoded default values (final fallback)
_HARDCODED_DEFAULTS = {
    "max_retries": 3,
    "parallel_batch_size": 4,
    "upload_connect_timeout": 30,
    "upload_read_timeout": 120,
    "thumbnail_size": 3,
    "thumbnail_format": 2,
    "auto_rename": True,
}


def get_image_host_setting(host_id: str, key: str, value_type: str = "str") -> Any:
    """Get an image host setting with 3-tier fallback.

    Lookup order:
      1. INI [IMAGE_HOSTS] section, key = f"{host_id}_{key}"
      2. (IMX only) INI [DEFAULTS] section, key = key  -- legacy compat
      3. ImageHostConfig.defaults[key] from JSON
      4. _HARDCODED_DEFAULTS[key]

    Args:
        host_id: Host identifier (e.g., 'imx')
        key: Setting name (e.g., 'thumbnail_size')
        value_type: 'str', 'bool', or 'int'

    Returns:
        Setting value from highest-priority source available.
    """
    from bbdrop import get_config_path

    ini_path = get_config_path()
    if os.path.exists(ini_path):
        with _ini_file_lock:
            cfg = configparser.ConfigParser()
            cfg.read(ini_path, encoding='utf-8')

            # Tier 1: INI [IMAGE_HOSTS] section
            if cfg.has_section("IMAGE_HOSTS"):
                ini_key = f"{host_id}_{key}"
                if cfg.has_option("IMAGE_HOSTS", ini_key):
                    try:
                        raw = cfg.get("IMAGE_HOSTS", ini_key)
                        if raw and raw.strip():
                            if value_type == "bool":
                                return cfg.getboolean("IMAGE_HOSTS", ini_key)
                            elif value_type == "int":
                                return cfg.getint("IMAGE_HOSTS", ini_key)
                            else:
                                return raw
                    except (ValueError, TypeError, configparser.Error):
                        pass  # Fall through

            # Tier 2: Legacy INI [DEFAULTS] section (IMX only)
            if host_id == "imx" and cfg.has_section("DEFAULTS"):
                if cfg.has_option("DEFAULTS", key):
                    try:
                        raw = cfg.get("DEFAULTS", key)
                        if raw and raw.strip():
                            if value_type == "bool":
                                return cfg.getboolean("DEFAULTS", key)
                            elif value_type == "int":
                                return cfg.getint("DEFAULTS", key)
                            else:
                                return raw
                    except (ValueError, TypeError, configparser.Error):
                        pass  # Fall through

    # Tier 3: JSON config defaults
    manager = get_image_host_config_manager()
    host = manager.hosts.get(host_id)
    if host and host.defaults and key in host.defaults:
        return host.defaults[key]

    # Tier 4: Hardcoded fallback
    if key in _HARDCODED_DEFAULTS:
        return _HARDCODED_DEFAULTS[key]

    log(f"Unknown image host setting requested: {key} for {host_id}",
        level="warning", category="image_hosts")
    return None


def save_image_host_setting(host_id: str, key: str, value: Any) -> None:
    """Write to INI [IMAGE_HOSTS] section as f"{host_id}_{key}".

    Does NOT delete legacy [DEFAULTS] keys (safe migration).
    """
    from bbdrop import get_config_path

    with _ini_file_lock:
        ini_path = get_config_path()
        cfg = configparser.ConfigParser()

        if os.path.exists(ini_path):
            cfg.read(ini_path, encoding='utf-8')

        if not cfg.has_section("IMAGE_HOSTS"):
            cfg.add_section("IMAGE_HOSTS")

        ini_key = f"{host_id}_{key}"
        cfg.set("IMAGE_HOSTS", ini_key, str(value))

        try:
            with open(ini_path, 'w', encoding='utf-8') as f:
                cfg.write(f)
        except Exception as e:
            log(f"Error saving image host setting {key} for {host_id}: {e}",
                level="error", category="image_hosts")
            raise


class ImageHostConfigManager:
    """Manages loading and accessing image host configurations."""

    def __init__(self):
        self.hosts: Dict[str, ImageHostConfig] = {}
        self.builtin_dir = self._get_builtin_hosts_dir()
        self.custom_dir = self._get_custom_hosts_dir()

    def _get_builtin_hosts_dir(self) -> Path:
        """Get path to built-in image host configs."""
        from bbdrop import get_project_root
        return Path(get_project_root()) / "assets" / "image_hosts"

    def _get_custom_hosts_dir(self) -> Path:
        """Get path to user custom image host configs."""
        from bbdrop import get_central_store_base_path
        hosts_dir = Path(get_central_store_base_path()) / "image_hosts"
        hosts_dir.mkdir(parents=True, exist_ok=True)
        return hosts_dir

    def load_all(self) -> None:
        """Load all image host configurations."""
        self.hosts.clear()

        if self.builtin_dir.exists():
            self._load_from_dir(self.builtin_dir)
        else:
            log(f"Built-in image hosts directory does not exist: {self.builtin_dir}",
                level="warning", category="image_hosts")

        if self.custom_dir.exists():
            self._load_from_dir(self.custom_dir)

    def _load_from_dir(self, directory: Path) -> None:
        """Load image host configs from a directory."""
        for json_file in directory.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if not isinstance(data, dict):
                    raise ValueError(f"Config must be a dictionary, got {type(data)}")
                if 'name' not in data:
                    raise ValueError("Config missing required field: 'name'")

                host_id = json_file.stem
                self.hosts[host_id] = ImageHostConfig.from_dict(host_id, data)

            except Exception as e:
                log(f"Error loading image host config {json_file}: {e}",
                    level="error", category="image_hosts")

    def get_host(self, host_id: str) -> Optional[ImageHostConfig]:
        """Get a host configuration by ID."""
        return self.hosts.get(host_id)

    def get_enabled_hosts(self) -> Dict[str, ImageHostConfig]:
        """Get all enabled host configurations (Phase 1: all loaded hosts)."""
        return dict(self.hosts)

    def list_hosts(self) -> List[str]:
        """List all host IDs."""
        return list(self.hosts.keys())


# Global singleton
_config_manager: Optional[ImageHostConfigManager] = None


def get_image_host_config_manager() -> ImageHostConfigManager:
    """Get or create the global ImageHostConfigManager instance (thread-safe)."""
    global _config_manager

    if _config_manager is None:
        with _config_manager_lock:
            if _config_manager is None:
                _config_manager = ImageHostConfigManager()
                _config_manager.load_all()
    return _config_manager
