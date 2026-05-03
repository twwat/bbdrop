"""Host registry — single source of truth for host identity.

Two directions of resolution:
- get_display_name(host_id) → user-facing label (e.g. 'imx' → 'imx.to')
- to_host_id(any_string)    → canonical id from any variant
                              ('imx.to' / 'IMX' / 'imx' / 'TurboImageHost' → 'imx' / 'imx' / 'imx' / 'turbo')

All UI code should use get_display_name for rendering.
All matching/lookup code should normalize inputs through to_host_id.
"""

from typing import Dict, List

from src.utils.logger import log


_DISPLAY_NAMES: Dict[str, str] = {}
_REVERSE_LOOKUP: Dict[str, str] = {}  # any-form-lowercased → canonical host_id


def _register(host_id: str, display_name: str) -> None:
    """Add a host to both forward (id→display) and reverse (any→id) maps."""
    _DISPLAY_NAMES[host_id] = display_name
    # Register every variant we might see as input → canonical host_id
    _REVERSE_LOOKUP[host_id.lower()] = host_id
    _REVERSE_LOOKUP[display_name.lower()] = host_id


def _init_registry() -> None:
    """Load display names from both config managers into the module cache."""
    try:
        from src.core.image_host_config import get_image_host_config_manager
        mgr = get_image_host_config_manager()
        for host_id, cfg in mgr.get_all_hosts().items():
            _register(host_id, cfg.name)
    except Exception as e:
        log(f"Failed to load image host configs for registry: {e}",
            level="warning", category="core")

    try:
        from src.core.file_host_config import get_config_manager
        mgr = get_config_manager()
        for host_id, cfg in mgr.hosts.items():
            _register(host_id, cfg.name)
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


def to_host_id(value: str) -> str:
    """Resolve any host-shaped string to its canonical host_id.

    Accepts host_ids (any case), display names (any case), or anything
    registered via _register. Returns the lowercased input as a best-effort
    fallback when nothing matches — that way storage keys stay stable across
    callers passing odd casing, even before the host has been registered.

    Examples (after registry is loaded):
        to_host_id('imx')           -> 'imx'
        to_host_id('IMX')           -> 'imx'
        to_host_id('imx.to')        -> 'imx'
        to_host_id('Imx.to')        -> 'imx'
        to_host_id('TurboImageHost')-> 'turbo'
        to_host_id('Pixhost')       -> 'pixhost'
    """
    if not value:
        return ''
    if not _DISPLAY_NAMES:
        _init_registry()
    return _REVERSE_LOOKUP.get(value.lower(), value.lower())
