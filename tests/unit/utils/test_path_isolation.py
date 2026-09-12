"""The test suite must never touch the user's real ~/.bbdrop.

On 2026-08-25 and again on 2026-09-12, running the GUI tests destroyed the
user's live bbdrop.ini: all 7 *_bbcode_format values and the filedot_* tuning
keys, including filedot_trigger, whose loss silently stopped FileDot uploads
from being queued at all.

Cause: GUI tests construct real settings dialogs, whose save_to_config()
writes to get_config_path() -- the user's actual file -- and tests/conftest.py
had no isolation for it.

See docs/superpowers/specs/2026-09-12-test-config-isolation.md
"""

import os
from pathlib import Path

import pytest

from src.utils import paths


@pytest.mark.unit
class TestBasePathOverride:

    def test_env_var_wins(self, tmp_path, monkeypatch):
        """BBDROP_BASE_PATH must take precedence over every other source."""
        monkeypatch.setenv("BBDROP_BASE_PATH", str(tmp_path))

        assert paths.get_base_path() == str(tmp_path)

    def test_config_path_follows_the_override(self, tmp_path, monkeypatch):
        """get_config_path() derives from get_base_path(), so it must follow."""
        monkeypatch.setenv("BBDROP_BASE_PATH", str(tmp_path))

        assert Path(paths.get_config_path()) == tmp_path / "bbdrop.ini"

    def test_central_store_base_follows_the_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BBDROP_BASE_PATH", str(tmp_path))

        assert paths.get_central_store_base_path() == str(tmp_path)

    def test_default_central_store_base_follows_the_override(self, tmp_path, monkeypatch):
        """general_tab writes a bbdrop.ini into this path on save, so it must
        divert under test even though it is NOT get_base_path()."""
        monkeypatch.setenv("BBDROP_BASE_PATH", str(tmp_path))

        assert paths.get_default_central_store_base_path() == str(tmp_path)

    def test_default_central_store_base_stays_home_in_production(self, monkeypatch):
        """Without the override it must remain the HOME location, distinct
        from get_base_path(). general_tab compares the two to decide whether
        the user is on home / portable / custom; collapsing them makes
        "Custom location" unselectable (general_tab.py:136)."""
        monkeypatch.delenv("BBDROP_BASE_PATH", raising=False)

        expected = os.path.join(os.path.expanduser("~"), ".bbdrop")
        assert paths.get_default_central_store_base_path() == expected

    def test_blank_override_is_ignored(self, tmp_path, monkeypatch):
        """An empty value must not resolve the base path to ''."""
        monkeypatch.setenv("BBDROP_BASE_PATH", "")

        assert paths.get_base_path() != ""

    def test_falls_back_when_unset(self, monkeypatch):
        """Without the override, normal resolution is unchanged.

        Deliberately pins BOTH other sources. After Task 2 this is the one
        test in the suite that de-isolates itself, so it must not depend on
        the machine it runs on: `.endswith(".bbdrop")` would fail for any
        user whose QSettings custom base path is named something else.
        """
        monkeypatch.delenv("BBDROP_BASE_PATH", raising=False)

        # Force the QSettings branch to miss, so we test the documented
        # final fallback rather than whatever this machine has configured.
        class _NoCustomBase:
            def __init__(self, *a, **kw):
                pass

            def value(self, *a, **kw):
                return ""

        monkeypatch.setattr("PyQt6.QtCore.QSettings", _NoCustomBase)

        expected = os.path.join(os.path.expanduser("~"), ".bbdrop")
        assert paths.get_base_path() == expected
