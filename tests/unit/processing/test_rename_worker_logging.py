"""GUI-visible rename worker messages must name the service.

The main-window log pane strips the [category] tag when the "show category"
setting is off (main_window.py:2687-2695), so `Not logged in` was
indistinguishable from a file-host message — which is exactly how a stale
FileDot session got mistaken for an IMX re-authentication on 2026-09-08.

RenameWorker is IMX-only (CLAUDE.md), so every info/warning message in it
is an IMX message. Debug messages are excluded: they aren't shown in the
GUI at the default level.

See docs/superpowers/specs/2026-09-08-xfs-session-validation.md (R8).
"""

import inspect
import re

import pytest

import src.processing.rename_worker as rename_worker


@pytest.mark.unit
class TestRenameWorkerLogPrefixes:

    def test_visible_messages_name_the_service(self):
        source = inspect.getsource(rename_worker)

        # Every log(...) call with a literal first argument and an
        # info/warning level. `[^)]*?` cannot cross a ')', so a match can
        # never pair one call's message with another call's level=.
        pattern = re.compile(
            r'log\(\s*f?"([^"]+)"[^)]*?level=["\'](info|warning)["\']',
            re.DOTALL,
        )
        found = pattern.findall(source)

        # Guard against the regex silently matching nothing and the test
        # passing vacuously.
        assert len(found) >= 15, (
            f"expected at least 15 GUI-visible log calls, found {len(found)} — "
            "the regex has probably stopped matching"
        )

        offenders = [msg for msg, _level in found if not msg.startswith("IMX:")]

        assert offenders == [], (
            "GUI-visible rename worker messages must start with 'IMX:' so the "
            f"log names the service. Unprefixed: {offenders}"
        )
