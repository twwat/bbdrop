"""Host display name registry — single source of truth.

Loads canonical display names from image host and file host JSON configs
once per process. All UI code should use get_display_name(host_id) instead
of ad-hoc .title(), .upper(), HOST_LABELS dicts, or config.name lookups.
"""

from typing import Dict, List

from src.utils.logger import log


_DISPLAY_NAMES: Dict[str, str] = {}


def _init_registry() -> None:
    """Load display names from both config managers into the module cache."""
    try:
        from src.core.image_host_config import get_image_host_config_manager
        mgr = get_image_host_config_manager()
        for host_id, cfg in mgr.get_all_hosts().items():
            _DISPLAY_NAMES[host_id] = cfg.name
    except Exception as e:
        log(f"Failed to load image host configs for registry: {e}",
            level="warning", category="core")

    try:
        from src.core.file_host_config import get_config_manager
        mgr = get_config_manager()
        for host_id, cfg in mgr.hosts.items():
            _DISPLAY_NAMES[host_id] = cfg.name
    except Exception as e:
        log(f"Failed to load file host configs for registry: {e}",
            level="warning", category="core")


def get_display_name(host_id: str) -> str:
    """Return the canonical display name for a host_id.

    Loads from JSON configs on first call, cached thereafter.
    Returns host_id unchanged if not found.
    """
    if not _DISPLAY_NAMES:
        _init_registry()
    return _DISPLAY_NAMES.get(host_id, host_id)


def get_all_host_ids() -> List[str]:
    """Return all known host_ids (image + file hosts)."""
    if not _DISPLAY_NAMES:
        _init_registry()
    return list(_DISPLAY_NAMES.keys())
