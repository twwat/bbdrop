"""Module-level Qt signal hub for cross-cutting forum-poster signals.

Anything that regenerates a gallery's BBCode emits ``bbcode_regenerated``
with (gallery_id, cause). The forum controller subscribes and decides
what to do (auto-post on upload, stale-mark on template edit, etc.).

The hub is exposed via ``get_signal_hub()`` because PyQt may delete the
underlying C++ QObject when a QApplication is destroyed (common in test
runs that recreate apps); the getter rebuilds it transparently.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §7.6.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal


class _ForumSignalHub(QObject):
    bbcode_regenerated = pyqtSignal(int, str)   # gallery_id, cause


_hub: _ForumSignalHub | None = None


def get_signal_hub() -> _ForumSignalHub:
    global _hub
    if _hub is None:
        _hub = _ForumSignalHub()
        return _hub
    try:
        # Poke a no-op attr to detect deleted C++ object.
        _hub.objectName()
        return _hub
    except RuntimeError:
        _hub = _ForumSignalHub()
        return _hub


class _HubProxy:
    """Attribute-forwarding proxy so existing
    ``bbcode_regenerated_signal_hub.bbcode_regenerated`` access keeps working
    while we transparently rebuild the underlying QObject if PyQt deletes it."""

    @property
    def bbcode_regenerated(self):
        return get_signal_hub().bbcode_regenerated


bbcode_regenerated_signal_hub = _HubProxy()
