"""Stable string keys for settings tabs.

Tabs used to be referenced by integer indexes, which silently desynced
whenever a tab was inserted/reordered (e.g. adding Forums bumped every
subsequent tab by one but the constants kept pointing at the old slots).

These are string keys — the settings dialog registers each page's key as
it's added and exposes a key→index map. Callers always pass the key;
the dialog resolves the current index at call time.
"""


class TabIndex:
    GENERAL = "general"
    HOSTS = "hosts"
    FORUMS = "forums"
    TEMPLATES = "templates"
    IMAGE_SCAN = "image_scan"
    COVERS = "covers"
    HOOKS = "hooks"
    PROXY = "proxy"
    LOGS = "logs"
    NOTIFICATIONS = "notifications"
    ARCHIVE = "archive"
    VIDEO = "video"
    ADVANCED = "advanced"
