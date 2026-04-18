"""Preset layouts for the customizable dock system.

Each value is the base64-encoded output of QByteArray(mw.saveState()).toBase64().data().
Empty bytes (b"") means the payload has not yet been captured — applying such a preset
is a no-op with a logged warning. Payloads are captured once during development by
manually arranging the app and reading mw.saveState(); see Task 6.
"""

PRESETS: dict[str, bytes] = {
    "classic":       b"",
    "focused_queue": b"",
    "two_column":    b"",
}
