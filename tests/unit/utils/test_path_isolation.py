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


@pytest.mark.unit
class TestSuiteWideIsolation:
    """These assert the autouse fixture is actually in force. They take no
    fixture of their own on purpose -- if isolation only worked when a test
    asked for it, it would not have prevented the incident."""

    def test_base_path_is_not_the_real_home(self):
        real = Path(os.path.expanduser("~")).resolve() / ".bbdrop"
        assert Path(paths.get_base_path()).resolve() != real, (
            "tests are resolving to the user's real ~/.bbdrop -- the autouse "
            "isolation fixture in tests/conftest.py is missing or bypassed"
        )

    def test_config_path_is_not_the_real_ini(self):
        real = Path(os.path.expanduser("~")).resolve() / ".bbdrop" / "bbdrop.ini"
        assert Path(paths.get_config_path()).resolve() != real, (
            "tests would write the user's real bbdrop.ini"
        )

    def test_override_is_actually_set(self):
        assert os.environ.get("BBDROP_BASE_PATH"), (
            "BBDROP_BASE_PATH is unset during the run; isolation is not active"
        )


@pytest.mark.unit
class TestNoHardcodedHomePaths:

    # Allowed (path, literal) pairs -- NOT whole files.
    #
    # Keying on the file alone would mean a NEW hardcoded path added to an
    # allowlisted file is invisible forever. That matters most for
    # general_tab.py, which is a settings tab that writes config: the exact
    # file class that caused this bug.
    # Allowed (path, line, literal) triples -- NOT whole files, and NOT
    # (path, literal) either. Literal-keying would let a NEW hardcoded
    # ~/.bbdrop anywhere in an already-listed file pass silently. Line-keying
    # fails loudly when code moves, which is the safe direction: someone
    # re-verifies rather than a bypass slipping through.
    _ALLOWED = {
        # The one legitimate definition site.
        ("src/utils/paths.py", 98, ".bbdrop"),
        ("src/utils/paths.py", 186, ".bbdrop"),
        ("src/utils/paths.py", 328, ".bbdrop"),
        # Portable-install path: joined to the APP root, not the user's home,
        # so it cannot reach real user data.
        ("src/gui/settings/general_tab.py", 117, ".bbdrop"),
        ("src/gui/settings/general_tab.py", 477, ".bbdrop"),
        # Last-resort defaults, reached ONLY when src.utils.paths is itself
        # unavailable -- these sit inside `except` handlers whose whole purpose
        # is that get_base_path() could not be imported. No other value exists
        # at that point, and both try get_base_path() first.
        ("src/gui/main_window.py", 1515, "~/.bbdrop"),
        ("src/utils/artifact_finder.py", 50, ".bbdrop"),
    }

    def test_no_source_file_rebuilds_the_base_path_by_hand(self):
        """AST-based on purpose.

        A line-regex version of this test was blind to 4 of the 5 bypasses
        that existed when it was written: three used the `~/.bbdrop` tilde-path
        form rather than a bare `~`, and one split `expanduser("~")` and the
        `.bbdrop` join across two lines. It reported a clean bill of health
        while the worst offenders -- main_window's import-failure fallback,
        which is exactly what a GUI test with mocked imports hits -- sat
        untouched.

        Walking the AST for string constants catches every spelling, and
        skipping docstrings keeps the ~12 prose mentions of "~/.bbdrop" from
        drowning the signal.
        """
        import ast
        from pathlib import Path as P

        def docstring_nodes(tree):
            """Every Constant node that is a module/class/function docstring."""
            out = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef,
                                     ast.FunctionDef, ast.AsyncFunctionDef)):
                    body = getattr(node, "body", None)
                    if body and isinstance(body[0], ast.Expr) and \
                            isinstance(body[0].value, ast.Constant) and \
                            isinstance(body[0].value.value, str):
                        out.add(id(body[0].value))
            return out

        # Anchored to the repo, NOT the cwd. A bare P("src") resolves against
        # whatever directory pytest was invoked from, so running from anywhere
        # but the repo root would find zero files and pass vacuously -- a
        # guard test that silently certifies nothing.
        src_root = P(__file__).resolve().parents[3] / "src"
        assert src_root.is_dir(), f"expected src/ at {src_root}"

        offenders = []
        for path in sorted(src_root.rglob("*.py")):
            rel = path.relative_to(src_root.parent).as_posix()
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            skip = docstring_nodes(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                        and ".bbdrop" in node.value and id(node) not in skip:
                    if (rel, node.lineno, node.value) in self._ALLOWED:
                        continue
                    offenders.append(f"{rel}:{node.lineno} {node.value!r}")

        assert offenders == [], (
            "these build a ~/.bbdrop path by hand instead of calling "
            f"get_base_path(), so they escape test isolation: {offenders}"
        )

    # Helpers in system_utils.py that reach the user's profile WITHOUT ever
    # spelling ".bbdrop", so the AST test above is structurally blind to them.
    # get_app_data_directory() does app_dir.mkdir(parents=True, exist_ok=True)
    # under %APPDATA% / ~/Library/Application Support / ~/.config -- a real
    # write into the user's profile.
    _UNREACHABLE_HELPERS = (
        "get_home_directory",
        "get_app_data_directory",
        "get_temp_directory",
    )

    def test_profile_writing_helpers_stay_unreachable(self):
        """A REACHABILITY guard, deliberately SEPARATE from the AST test.

        The two answer different questions -- spelling vs. reachability.
        Folding this into the walker would mean allowlisting cookies.py
        (Firefox profiles), screenshot_sheet.py (font dirs) and general_tab.py
        wholesale, which is exactly the coarse whole-file allowlisting that
        makes a guard blind to future additions.

        These three have no callers in src/ today (only their own test file).
        This test exists so that stays true: the moment one is imported, it
        must be routed through get_base_path() first.
        """
        import re
        from pathlib import Path as P

        src_root = P(__file__).resolve().parents[3] / "src"
        pattern = re.compile("|".join(self._UNREACHABLE_HELPERS))

        importers = []
        for path in sorted(src_root.rglob("*.py")):
            rel = path.relative_to(src_root.parent).as_posix()
            if rel == "src/utils/system_utils.py":   # definition site
                continue
            for i, line in enumerate(
                    path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if pattern.search(line):
                    importers.append(f"{rel}:{i}")

        assert importers == [], (
            "these write into the user's profile and are invisible to the "
            f".bbdrop guard; route them through get_base_path() first: {importers}"
        )
