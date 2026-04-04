"""Verify IMX-specific startup credential check has been removed."""
import pytest


class TestStartupCredentialCheckRemoved:
    """The IMX-specific startup check should not exist."""

    def test_no_check_credentials_method(self):
        """BBDropGUI should not have a check_credentials method."""
        import ast
        with open("src/gui/main_window.py") as f:
            tree = ast.parse(f.read())

        methods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                methods.append(node.name)

        assert "check_credentials" not in methods
        assert "check_stored_credentials" not in methods
        assert "api_key_is_set" not in methods

    def test_no_has_imx_credentials_function(self):
        """Module-level has_imx_credentials should not exist."""
        import ast
        with open("src/gui/main_window.py") as f:
            tree = ast.parse(f.read())

        top_level_funcs = [
            node.name for node in ast.iter_child_nodes(tree)
            if isinstance(node, ast.FunctionDef)
        ]

        assert "has_imx_credentials" not in top_level_funcs
        assert "check_stored_credentials" not in top_level_funcs
        assert "api_key_is_set" not in top_level_funcs
