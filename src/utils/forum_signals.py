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


# ---------------------------------------------------------------------------
# Helper emitters used by non-forum code paths that regenerate BBCode.
# ForumController.on_bbcode_regenerated filters by stale_triggers, so coarse
# broadcasts are safe — unconfigured causes are ignored.
# ---------------------------------------------------------------------------

def emit_template_edit(template_name: str) -> None:
    """Emit ``bbcode_regenerated(gid, 'template_edit')`` for every gallery
    whose ``template`` column matches ``template_name``. Silent on error."""
    if not template_name:
        return
    try:
        from src.storage.database import _connect
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT id FROM galleries WHERE template=?",
                (template_name,),
            ).fetchall()
        finally:
            conn.close()
        hub = get_signal_hub()
        for r in rows:
            hub.bbcode_regenerated.emit(int(r[0]), "template_edit")
    except Exception:
        pass


def emit_link_format_changed() -> None:
    """Emit ``bbcode_regenerated(gid, 'link_format')`` for every gallery that
    has a live forum_post (posted/stale/queued/posting/updating). Silent on
    error — forum_controller filters by stale_triggers before acting."""
    try:
        from src.storage.database import _connect
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT DISTINCT gallery_fk FROM forum_posts "
                "WHERE status IN ('posted','stale','queued','posting','updating')"
            ).fetchall()
        finally:
            conn.close()
        hub = get_signal_hub()
        for r in rows:
            hub.bbcode_regenerated.emit(int(r[0]), "link_format")
    except Exception:
        pass


def emit_manual_rerender(gallery_id: int) -> None:
    """Emit ``bbcode_regenerated(gid, 'manual_rerender')``. Silent on error."""
    if not gallery_id:
        return
    try:
        get_signal_hub().bbcode_regenerated.emit(int(gallery_id), "manual_rerender")
    except Exception:
        pass
