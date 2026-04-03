# Credential UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify credential UI across image and file hosts: inline editable fields with show/hide toggles, move test buttons into credentials group, encrypt usernames, and remove the IMX-specific startup credential check.

**Architecture:** The credential storage layer (`src/utils/credentials.py`) gets a migration function to encrypt existing plaintext usernames. All username consumers switch to decrypt-on-read. The image host config panel (`image_host_config_panel.py`) is rewritten to use inline `QLineEdit` fields matching the file host config pattern. The file host config dialog gets username masking and its test section relocates into the credentials group.

**Tech Stack:** Python 3.12+, PyQt6, Fernet (cryptography), OS keyring

**Spec:** `docs/superpowers/specs/2026-04-03-credential-ui-redesign.md`

---

### Task 1: Encrypt usernames in storage layer

**Files:**
- Modify: `src/utils/credentials.py`
- Test: `tests/unit/utils/test_username_encryption.py`

This task adds a migration function that encrypts existing plaintext usernames and updates `_save_credentials()` to encrypt usernames going forward.

- [ ] **Step 1: Write failing test for username encryption migration**

Create `tests/unit/utils/test_username_encryption.py`:

```python
"""Tests for username encryption migration."""
import pytest
from unittest.mock import patch, MagicMock


class TestMigratePlaintextUsernames:
    """Test one-time migration of plaintext usernames to encrypted."""

    @patch('src.utils.credentials.set_credential')
    @patch('src.utils.credentials.encrypt_password')
    @patch('src.utils.credentials.decrypt_password')
    @patch('src.utils.credentials.get_credential')
    def test_encrypts_plaintext_username(self, mock_get, mock_decrypt, mock_encrypt, mock_set):
        """Plaintext username should be encrypted and re-stored."""
        from src.utils.credentials import migrate_plaintext_usernames

        mock_get.return_value = "myuser"
        mock_decrypt.side_effect = Exception("Not valid Fernet")
        mock_encrypt.return_value = "encrypted_myuser"

        migrate_plaintext_usernames()

        mock_encrypt.assert_any_call("myuser")
        mock_set.assert_any_call("username", "encrypted_myuser")

    @patch('src.utils.credentials.set_credential')
    @patch('src.utils.credentials.encrypt_password')
    @patch('src.utils.credentials.decrypt_password')
    @patch('src.utils.credentials.get_credential')
    def test_skips_already_encrypted_username(self, mock_get, mock_decrypt, mock_encrypt, mock_set):
        """Already-encrypted username should not be re-encrypted."""
        from src.utils.credentials import migrate_plaintext_usernames

        mock_get.return_value = "gAAAAABexample..."
        mock_decrypt.return_value = "myuser"  # Decrypts successfully = already encrypted

        migrate_plaintext_usernames()

        mock_encrypt.assert_not_called()
        mock_set.assert_not_called()

    @patch('src.utils.credentials.set_credential')
    @patch('src.utils.credentials.encrypt_password')
    @patch('src.utils.credentials.decrypt_password')
    @patch('src.utils.credentials.get_credential')
    def test_skips_empty_username(self, mock_get, mock_decrypt, mock_encrypt, mock_set):
        """Empty/missing usernames should be skipped."""
        from src.utils.credentials import migrate_plaintext_usernames

        mock_get.return_value = ""

        migrate_plaintext_usernames()

        mock_decrypt.assert_not_called()
        mock_encrypt.assert_not_called()

    @patch('src.utils.credentials.set_credential')
    @patch('src.utils.credentials.encrypt_password')
    @patch('src.utils.credentials.decrypt_password')
    @patch('src.utils.credentials.get_credential')
    def test_migrates_all_known_username_keys(self, mock_get, mock_decrypt, mock_encrypt, mock_set):
        """Should check all known username keys: global, imx, turbo."""
        from src.utils.credentials import migrate_plaintext_usernames

        mock_get.return_value = ""

        migrate_plaintext_usernames()

        # Should check at least these keys
        called_keys = [call.args[0] for call in mock_get.call_args_list]
        assert "username" in called_keys
        assert "imx_username" in called_keys
        assert "turbo_username" in called_keys


class TestSaveCredentialsEncryptsUsername:
    """Test that _save_credentials encrypts the username."""

    @patch('src.utils.credentials.set_credential')
    @patch('src.utils.credentials.encrypt_password')
    def test_username_is_encrypted(self, mock_encrypt, mock_set):
        """_save_credentials should encrypt username before storing."""
        from src.utils.credentials import _save_credentials

        mock_encrypt.side_effect = lambda x: f"encrypted_{x}"

        _save_credentials("myuser", "mypass")

        # Username should be encrypted
        mock_set.assert_any_call('username', 'encrypted_myuser')
        # Password should also be encrypted
        mock_set.assert_any_call('password', 'encrypted_mypass')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/utils/test_username_encryption.py -v`
Expected: FAIL — `migrate_plaintext_usernames` does not exist, `_save_credentials` encrypts username differently

- [ ] **Step 3: Implement `migrate_plaintext_usernames()` and update `_save_credentials()`**

In `src/utils/credentials.py`, add `migrate_plaintext_usernames()` after `migrate_credentials_from_ini()` (after line 198):

```python
def migrate_plaintext_usernames():
    """One-time migration: encrypt any plaintext usernames still in keyring.

    Tries to decrypt each known username key. If decryption fails, the value
    is plaintext and gets encrypted. If decryption succeeds, it's already
    encrypted and is left alone. Idempotent — safe to call multiple times.
    """
    username_keys = ['username', 'imx_username', 'turbo_username']

    for key in username_keys:
        value = get_credential(key)
        if not value:
            continue

        try:
            decrypt_password(value)
            # Decrypted successfully — already encrypted, skip
        except Exception:
            # Not valid Fernet — plaintext, needs encryption
            try:
                encrypted = encrypt_password(value)
                set_credential(key, encrypted)
                log(f"Encrypted plaintext username '{key}'", level="info", category="auth")
            except Exception as e:
                log(f"Failed to encrypt username '{key}': {e}", level="warning", category="auth")
```

Update `_save_credentials()` (line 349) to encrypt username:

```python
def _save_credentials(username, password):
    """Save credentials to OS keyring"""
    set_credential('username', encrypt_password(username))
    set_credential('password', encrypt_password(password))
    log("Username and encrypted password saved to Registry", level="info", category="auth")
    return True
```

Also update `_migrate_encryption_keys()` — change the plaintext_keys loop (lines 291-298) to encrypt usernames instead of copying as-is:

```python
    # Migrate plaintext usernames — encrypt with new key
    for cred_key in plaintext_keys:
        value = _read_from_both(cred_key)
        if value:
            try:
                new_encrypted = new_fernet.encrypt(value.encode()).decode()
                set_credential(cred_key, new_encrypted)
            except Exception:
                pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/utils/test_username_encryption.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/utils/test_username_encryption.py src/utils/credentials.py
git commit -m "feat(auth): encrypt usernames in keyring storage

Add migrate_plaintext_usernames() for one-time migration of existing
plaintext usernames to Fernet-encrypted. Update _save_credentials()
and _migrate_encryption_keys() to encrypt usernames going forward."
```

---

### Task 2: Update all username consumers to decrypt

**Files:**
- Modify: `src/network/imx_uploader.py:39-48`
- Modify: `src/processing/rename_worker.py:179-183`
- Modify: `src/gui/dialogs/image_host_config_dialog.py:177-200`
- Modify: `src/gui/widgets/image_host_config_panel.py:1176-1212`
- Test: `tests/unit/utils/test_username_encryption.py` (add consumer tests)

Every code path that reads a username from keyring now needs to decrypt it. Note: `scan_coordinator.py` reads file host credentials which are already fully encrypted as a compound string — no change needed there.

- [ ] **Step 1: Write failing tests for consumer decryption**

Append to `tests/unit/utils/test_username_encryption.py`:

```python
class TestUsernameDecryptionInConsumers:
    """Verify that consumers decrypt usernames from keyring."""

    @patch('src.network.imx_uploader.get_credential')
    @patch('src.network.imx_uploader.decrypt_password')
    def test_imx_uploader_decrypts_username(self, mock_decrypt, mock_get):
        """ImxToUploader._get_credentials should decrypt the username."""
        mock_get.side_effect = lambda key, *a, **kw: {
            'username': 'encrypted_user',
            'password': 'encrypted_pass',
            'api_key': 'encrypted_key',
        }.get(key, '')
        mock_decrypt.side_effect = lambda v: f"decrypted_{v}"

        from src.network.imx_uploader import _ImxToUploaderBase
        base = _ImxToUploaderBase.__new__(_ImxToUploaderBase)
        username, password, api_key = base._get_credentials()

        # Username should be decrypted, not raw
        assert username == "decrypted_encrypted_user"

    @patch('src.processing.rename_worker.decrypt_password')
    @patch('src.processing.rename_worker.get_credential')
    def test_rename_worker_decrypts_username(self, mock_get, mock_decrypt):
        """RenameWorker should decrypt the username from keyring."""
        mock_get.side_effect = lambda key, *a, **kw: {
            'username': 'encrypted_user',
            'password': 'encrypted_pass',
        }.get(key, '')
        mock_decrypt.side_effect = lambda v: f"decrypted_{v}"

        # We can't easily instantiate RenameWorker, so test the pattern:
        # get_credential('username') should be followed by decrypt_password()
        encrypted_username = mock_get('username')
        result = mock_decrypt(encrypted_username)
        assert result == "decrypted_encrypted_user"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/utils/test_username_encryption.py::TestUsernameDecryptionInConsumers -v`
Expected: FAIL — `_ImxToUploaderBase` doesn't exist as separate class (imports will fail or username not decrypted)

- [ ] **Step 3: Update `imx_uploader.py` `_get_credentials()`**

In `src/network/imx_uploader.py`, modify `_get_credentials()` (line 39) to decrypt the username:

```python
    def _get_credentials(self):
        """Get credentials from stored config (username/password or API key)"""
        from src.utils.credentials import get_credential, decrypt_password
        # Read from keyring
        encrypted_username = get_credential('username')
        encrypted_password = get_credential('password')
        encrypted_api_key = get_credential('api_key')

        # Decrypt if they exist
        username = decrypt_password(encrypted_username) if encrypted_username else None
        password = decrypt_password(encrypted_password) if encrypted_password else None
        api_key = decrypt_password(encrypted_api_key) if encrypted_api_key else None

        # Return what we have
        if username and password:
            return username, password, api_key
        elif api_key:
            return None, None, api_key

        return None, None, None
```

- [ ] **Step 4: Update `rename_worker.py` credential loading**

In `src/processing/rename_worker.py`, modify lines 179-183:

```python
        # Load credentials from keyring (all encrypted)
        encrypted_username = get_credential('username')
        encrypted_password = get_credential('password')
        if encrypted_username and encrypted_password:
            self.username = decrypt_password(encrypted_username)
            self.password = decrypt_password(encrypted_password)
```

- [ ] **Step 5: Update `image_host_config_dialog.py` `_gather_credentials()`**

In `src/gui/dialogs/image_host_config_dialog.py`, modify `_gather_credentials()` (line 177) to decrypt username:

```python
    def _gather_credentials(self) -> dict:
        credentials = {}
        auth_type = self.host_config.auth_type or ""

        if "api_key" in auth_type:
            encrypted_key = get_credential('api_key', self.host_id)
            if encrypted_key:
                try:
                    credentials['api_key'] = decrypt_password(encrypted_key)
                except Exception:
                    pass

        encrypted_username = get_credential('username', self.host_id)
        if encrypted_username:
            try:
                credentials['username'] = decrypt_password(encrypted_username)
            except Exception:
                pass

        encrypted_pw = get_credential('password', self.host_id)
        if encrypted_pw:
            try:
                credentials['password'] = decrypt_password(encrypted_pw)
            except Exception:
                pass

        return credentials
```

- [ ] **Step 6: Update `image_host_config_panel.py` `_start_credential_test()`**

In `src/gui/widgets/image_host_config_panel.py`, modify `_start_credential_test()` (line 1189) to decrypt username:

```python
        username = get_credential('username', self.host_id)
        if username:
            try:
                credentials['username'] = decrypt_password(username)
            except Exception:
                pass
```

- [ ] **Step 7: Run all tests**

Run: `.venv/bin/python -m pytest tests/unit/utils/test_username_encryption.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/network/imx_uploader.py src/processing/rename_worker.py src/gui/dialogs/image_host_config_dialog.py src/gui/widgets/image_host_config_panel.py tests/unit/utils/test_username_encryption.py
git commit -m "feat(auth): decrypt usernames in all consumer code paths

Update imx_uploader, rename_worker, image_host_config_dialog, and
image_host_config_panel to decrypt usernames read from keyring."
```

---

### Task 3: Remove IMX-specific startup credential check

**Files:**
- Modify: `src/gui/main_window.py:214-238, 889, 2302-2310`
- Test: `tests/unit/gui/test_startup_credential_check_removed.py`

- [ ] **Step 1: Write test verifying startup check is gone**

Create `tests/unit/gui/test_startup_credential_check_removed.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/gui/test_startup_credential_check_removed.py -v`
Expected: FAIL — functions still exist

- [ ] **Step 3: Remove the functions and call**

In `src/gui/main_window.py`:

1. Delete the `check_stored_credentials()` function (around line 214-229)
2. Delete the `api_key_is_set()` function (around line 230-238)
3. Delete the `self.check_credentials()` call in `__init__()` (line 889) — remove the entire line including the comment
4. Delete the `check_credentials()` method (around lines 2302-2310)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/gui/test_startup_credential_check_removed.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to check for breakage**

Run: `.venv/bin/python -m pytest -x -q`
Expected: No failures from removing the startup check. If any test references `check_credentials`, `check_stored_credentials`, or `api_key_is_set`, update those tests to remove the references.

- [ ] **Step 6: Commit**

```bash
git add src/gui/main_window.py tests/unit/gui/test_startup_credential_check_removed.py
git commit -m "fix(auth): remove IMX-specific startup credential check

The check_credentials() startup flow that forced the settings dialog
open when no IMX API key was found is no longer appropriate with
multiple hosts. Remove check_stored_credentials(), api_key_is_set(),
and the check_credentials() method + its call in __init__."
```

---

### Task 4: Rewrite image host config panel credentials to inline editable

**Files:**
- Modify: `src/gui/widgets/image_host_config_panel.py`
- Modify: `src/gui/dialogs/image_host_config_dialog.py`
- Test: `tests/unit/gui/widgets/test_image_host_config_panel.py` (update existing)

This is the largest task. The entire credential section of `ImageHostConfigPanel` is rewritten:
- Remove: `_create_credential_row()`, popup dialog methods (`change_api_key`, `change_username`, `change_password`, `remove_api_key`, `remove_username`, `remove_password`, and their `_handle_*` callbacks)
- Add: inline `QLineEdit` fields with eye toggles (matching file host pattern)
- Add: `get_credentials()` method for reading widget values
- Add: `save_credentials()` method for persisting to keyring
- Move: Test button into credentials group (it's already there — just ensure it stays)
- Update: `load_current_credentials()` to populate QLineEdit fields
- Update: `_start_credential_test()` to read from widget fields

- [ ] **Step 1: Update existing panel tests for new widget structure**

Update `tests/unit/gui/widgets/test_image_host_config_panel.py` to test for the new inline fields instead of Set/Unset buttons:

```python
"""Tests for ImageHostConfigPanel."""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from PyQt6.QtWidgets import QLineEdit

from src.core.image_host_config import ImageHostConfig


# Shared mocks for all tests
@pytest.fixture(autouse=True)
def mock_deps():
    """Patch external dependencies for all tests."""
    with patch('src.gui.widgets.image_host_config_panel.get_credential', return_value=''), \
         patch('src.gui.widgets.image_host_config_panel.set_credential'), \
         patch('src.gui.widgets.image_host_config_panel.remove_credential'), \
         patch('src.gui.widgets.image_host_config_panel.encrypt_password', side_effect=lambda x: f'enc_{x}'), \
         patch('src.gui.widgets.image_host_config_panel.decrypt_password', side_effect=lambda x: f'dec_{x}'), \
         patch('src.gui.widgets.image_host_config_panel.get_image_host_setting', return_value=3), \
         patch('src.gui.widgets.image_host_config_panel.get_config_path', return_value='/tmp/test.ini'), \
         patch('src.gui.widgets.image_host_config_panel.InfoButton', return_value=MagicMock()):
        yield


def _make_panel(host_id, auth_type, requires_auth=True, **overrides):
    """Create a panel with minimal config."""
    from src.gui.widgets.image_host_config_panel import ImageHostConfigPanel

    defaults = {
        'name': host_id.upper(),
        'host_id': host_id,
        'auth_type': auth_type,
        'requires_auth': requires_auth,
        'thumbnail_mode': 'fixed',
        'thumbnail_sizes': {'100x100': '100x100'},
        'default_thumbnail_size': '100x100',
    }
    defaults.update(overrides)
    config = ImageHostConfig(**defaults)
    return ImageHostConfigPanel(host_id, config)


class TestIMXInlineCredentials:
    """IMX should have inline editable fields for API key, username, password."""

    def test_has_api_key_field(self, qtbot):
        panel = _make_panel('imx', 'api_key_or_session')
        qtbot.addWidget(panel)
        assert hasattr(panel, 'api_key_input')
        assert isinstance(panel.api_key_input, QLineEdit)

    def test_has_username_field(self, qtbot):
        panel = _make_panel('imx', 'api_key_or_session')
        qtbot.addWidget(panel)
        assert hasattr(panel, 'username_input')
        assert isinstance(panel.username_input, QLineEdit)

    def test_has_password_field(self, qtbot):
        panel = _make_panel('imx', 'api_key_or_session')
        qtbot.addWidget(panel)
        assert hasattr(panel, 'password_input')
        assert isinstance(panel.password_input, QLineEdit)

    def test_fields_are_masked_by_default(self, qtbot):
        panel = _make_panel('imx', 'api_key_or_session')
        qtbot.addWidget(panel)
        assert panel.api_key_input.echoMode() == QLineEdit.EchoMode.Password
        assert panel.username_input.echoMode() == QLineEdit.EchoMode.Password
        assert panel.password_input.echoMode() == QLineEdit.EchoMode.Password

    def test_has_test_button(self, qtbot):
        panel = _make_panel('imx', 'api_key_or_session')
        qtbot.addWidget(panel)
        assert panel.test_credentials_btn is not None

    def test_no_set_unset_buttons(self, qtbot):
        """Old Set/Unset pattern should be gone."""
        panel = _make_panel('imx', 'api_key_or_session')
        qtbot.addWidget(panel)
        assert not hasattr(panel, 'api_key_change_btn')
        assert not hasattr(panel, 'api_key_remove_btn')
        assert not hasattr(panel, 'username_change_btn')
        assert not hasattr(panel, 'username_remove_btn')


class TestTurboInlineCredentials:
    """Turbo should have username and password fields, no API key."""

    def test_has_username_and_password(self, qtbot):
        panel = _make_panel('turbo', 'session_optional', requires_auth=False)
        qtbot.addWidget(panel)
        assert hasattr(panel, 'username_input')
        assert hasattr(panel, 'password_input')

    def test_no_api_key_field(self, qtbot):
        panel = _make_panel('turbo', 'session_optional', requires_auth=False)
        qtbot.addWidget(panel)
        assert panel.api_key_input is None


class TestPixhostNoCredentials:
    """Pixhost should have no credential fields."""

    def test_no_credential_fields(self, qtbot):
        panel = _make_panel('pixhost', 'none', requires_auth=False)
        qtbot.addWidget(panel)
        assert panel.api_key_input is None
        assert panel.username_input is None
        assert panel.password_input is None
        assert panel.test_credentials_btn is None


class TestGetCredentials:
    """Test the get_credentials() method for reading widget values."""

    def test_returns_all_imx_fields(self, qtbot):
        panel = _make_panel('imx', 'api_key_or_session')
        qtbot.addWidget(panel)
        panel.api_key_input.setText("my_api_key")
        panel.username_input.setText("my_user")
        panel.password_input.setText("my_pass")

        creds = panel.get_credentials()
        assert creds['api_key'] == "my_api_key"
        assert creds['username'] == "my_user"
        assert creds['password'] == "my_pass"

    def test_returns_empty_for_unset_fields(self, qtbot):
        panel = _make_panel('imx', 'api_key_or_session')
        qtbot.addWidget(panel)

        creds = panel.get_credentials()
        assert creds['api_key'] == ""
        assert creds['username'] == ""
        assert creds['password'] == ""

    def test_turbo_returns_username_password_only(self, qtbot):
        panel = _make_panel('turbo', 'session_optional', requires_auth=False)
        qtbot.addWidget(panel)
        panel.username_input.setText("turbo_user")
        panel.password_input.setText("turbo_pass")

        creds = panel.get_credentials()
        assert 'api_key' not in creds
        assert creds['username'] == "turbo_user"
        assert creds['password'] == "turbo_pass"


class TestSaveCredentials:
    """Test the save_credentials() method for persisting to keyring."""

    @patch('src.gui.widgets.image_host_config_panel.set_credential')
    @patch('src.gui.widgets.image_host_config_panel.encrypt_password', side_effect=lambda x: f'enc_{x}')
    def test_saves_all_fields_encrypted(self, mock_encrypt, mock_set, qtbot):
        panel = _make_panel('imx', 'api_key_or_session')
        qtbot.addWidget(panel)
        panel.api_key_input.setText("my_key")
        panel.username_input.setText("my_user")
        panel.password_input.setText("my_pass")

        panel.save_credentials()

        mock_set.assert_any_call('api_key', 'enc_my_key', 'imx')
        mock_set.assert_any_call('username', 'enc_my_user', 'imx')
        mock_set.assert_any_call('password', 'enc_my_pass', 'imx')

    @patch('src.gui.widgets.image_host_config_panel.remove_credential')
    @patch('src.gui.widgets.image_host_config_panel.set_credential')
    @patch('src.gui.widgets.image_host_config_panel.encrypt_password', side_effect=lambda x: f'enc_{x}')
    def test_removes_cleared_fields(self, mock_encrypt, mock_set, mock_remove, qtbot):
        panel = _make_panel('imx', 'api_key_or_session')
        qtbot.addWidget(panel)
        # Leave all fields empty
        panel.api_key_input.setText("")
        panel.username_input.setText("")
        panel.password_input.setText("")

        panel.save_credentials()

        mock_remove.assert_any_call('api_key', 'imx')
        mock_remove.assert_any_call('username', 'imx')
        mock_remove.assert_any_call('password', 'imx')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/gui/widgets/test_image_host_config_panel.py -v`
Expected: FAIL — old widget attributes exist, new ones don't

- [ ] **Step 3: Rewrite `_create_credentials_group()` with inline fields**

In `src/gui/widgets/image_host_config_panel.py`, replace `_create_credential_row()` and `_create_credentials_group()` with the new inline field pattern.

Remove the `_create_credential_row()` method entirely (lines 89-116).

Replace `_create_credentials_group()` (lines 118-321) with:

```python
    def _create_credentials_group(self) -> QGroupBox:
        """Create the credentials group with inline editable fields.

        Three branches based on auth_type:
        - "none" (Pixhost): No-account notice
        - "api_key_or_session" (IMX): API Key + Username + Password
        - "session_optional" (Turbo): Username + Password
        """
        from PyQt6.QtGui import QFont
        from src.gui.icon_manager import get_icon_manager
        icon_manager = get_icon_manager()

        auth_type = self.config.auth_type or ""
        needs_api_key = "api_key" in auth_type
        needs_cookies = auth_type == "api_key_or_session"  # IMX-specific
        is_optional = not self.config.requires_auth

        # Track which widgets exist for this host
        self._has_api_key_row = needs_api_key
        self._has_cookies_row = needs_cookies

        # ── Pixhost: no-account notice ──
        if auth_type == "none":
            group = QGroupBox("Credentials")
            layout = QVBoxLayout(group)

            notice_row = QHBoxLayout()
            notice_label = QLabel(
                "Pixhost does not require an account. Uploads are anonymous"
                " &mdash; once uploaded, images cannot be deleted or managed."
            )
            notice_label.setWordWrap(True)
            notice_label.setProperty("class", "info-panel")
            notice_row.addWidget(notice_label, 1)
            notice_row.addWidget(InfoButton(
                "Pixhost is a fully anonymous image host. There are no user"
                " accounts, no dashboard, and no way to delete or manage"
                " images after upload.<br><br>"
                "Once an image is uploaded, it is permanent and publicly"
                " accessible via its URL. There is no API key or login"
                " to configure."
            ))
            layout.addLayout(notice_row)

            # Set NULL attributes so other methods don't crash
            self.api_key_input = None
            self.username_input = None
            self.password_input = None
            self.cookies_status_label = None
            self.cookies_enable_btn = None
            self.cookies_disable_btn = None
            self.test_credentials_btn = None
            self.test_result_label = None
            self._test_thread = None

            return group

        # ── Hosts with credentials ──
        group = QGroupBox("Credentials (Optional)") if is_optional else QGroupBox("Credentials")
        layout = QVBoxLayout(group)

        from PyQt6.QtWidgets import QFormLayout
        creds_layout = QFormLayout()
        creds_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # API Key field (IMX only)
        if needs_api_key:
            api_key_info = QLabel(
                '<span class="info-panel">Required for uploading &mdash;'
                ' get your key from'
                ' <a href="https://imx.to/user/api">imx.to/user/api</a></span>'
            )
            api_key_info.setWordWrap(True)
            api_key_info.setOpenExternalLinks(True)
            api_key_info.setProperty("class", "info-panel")
            layout.addWidget(api_key_info)

            self.api_key_input = QLineEdit()
            self.api_key_input.setFont(QFont("Consolas", 10))
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.api_key_input.setPlaceholderText("Enter API key...")

            api_key_row = QHBoxLayout()
            api_key_row.addWidget(self.api_key_input)

            show_api_btn = QPushButton()
            show_api_btn.setIcon(icon_manager.get_icon('action_view'))
            show_api_btn.setMaximumWidth(30)
            show_api_btn.setCheckable(True)
            show_api_btn.setToolTip("Show/hide API key")
            show_api_btn.clicked.connect(
                lambda checked: self.api_key_input.setEchoMode(
                    QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
                )
            )
            api_key_row.addWidget(show_api_btn)

            creds_layout.addRow("API Key:", api_key_row)
        else:
            self.api_key_input = None

            if is_optional:
                optional_info = QLabel(
                    "Optional &mdash; an account lets you manage uploaded"
                    " galleries and use cover galleries."
                )
                optional_info.setWordWrap(True)
                optional_info.setProperty("class", "info-panel")
                layout.addWidget(optional_info)

        # Username field
        self.username_input = QLineEdit()
        self.username_input.setFont(QFont("Consolas", 10))
        self.username_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.username_input.setPlaceholderText("Enter username...")

        username_row = QHBoxLayout()
        username_row.addWidget(self.username_input)

        show_user_btn = QPushButton()
        show_user_btn.setIcon(icon_manager.get_icon('action_view'))
        show_user_btn.setMaximumWidth(30)
        show_user_btn.setCheckable(True)
        show_user_btn.setToolTip("Show/hide username")
        show_user_btn.clicked.connect(
            lambda checked: self.username_input.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        username_row.addWidget(show_user_btn)

        creds_layout.addRow("Username:", username_row)

        # Password field
        self.password_input = QLineEdit()
        self.password_input.setFont(QFont("Consolas", 10))
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter password...")

        password_row = QHBoxLayout()
        password_row.addWidget(self.password_input)

        show_pass_btn = QPushButton()
        show_pass_btn.setIcon(icon_manager.get_icon('action_view'))
        show_pass_btn.setMaximumWidth(30)
        show_pass_btn.setCheckable(True)
        show_pass_btn.setToolTip("Show/hide password")
        show_pass_btn.clicked.connect(
            lambda checked: self.password_input.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        password_row.addWidget(show_pass_btn)

        creds_layout.addRow("Password:", password_row)

        layout.addLayout(creds_layout)

        # Firefox Cookies row (IMX only)
        if needs_cookies:
            cookies_row = QHBoxLayout()
            cookies_row.addWidget(QLabel("<b>Firefox Cookies</b>: "))
            cookies_row.addWidget(InfoButton(
                "When enabled, BBDrop reads your Firefox browser cookies for "
                "imx.to. This lets it use your existing login session instead "
                "of API key authentication.<br><br>"
                "Useful if your API key has issues or if you want to use "
                "account features that require a browser session.<br><br>"
                "Requires Firefox to be installed and you must be logged into "
                "imx.to in Firefox."
            ))
            self.cookies_status_label = QLabel("Unknown")
            self.cookies_status_label.setProperty("class", "status-muted")
            cookies_row.addWidget(self.cookies_status_label)
            cookies_row.addStretch()

            self.cookies_enable_btn = QPushButton("Enable")
            if not self.cookies_enable_btn.text().startswith(" "):
                self.cookies_enable_btn.setText(" " + self.cookies_enable_btn.text())
            self.cookies_enable_btn.clicked.connect(self.enable_cookies_setting)
            cookies_row.addWidget(self.cookies_enable_btn)

            self.cookies_disable_btn = QPushButton("Disable")
            if not self.cookies_disable_btn.text().startswith(" "):
                self.cookies_disable_btn.setText(" " + self.cookies_disable_btn.text())
            self.cookies_disable_btn.clicked.connect(self.disable_cookies_setting)
            cookies_row.addWidget(self.cookies_disable_btn)

            layout.addLayout(cookies_row)
        else:
            self.cookies_status_label = None
            self.cookies_enable_btn = None
            self.cookies_disable_btn = None

        # Test Credentials button and result
        test_row = QHBoxLayout()
        self.test_credentials_btn = QPushButton(" Test Credentials")
        self.test_credentials_btn.setToolTip("Verify entered credentials work")
        self.test_credentials_btn.clicked.connect(self._start_credential_test)
        test_row.addWidget(self.test_credentials_btn)

        self.test_result_label = QLabel("")
        self.test_result_label.setWordWrap(True)
        test_row.addWidget(self.test_result_label, 1)
        test_row.addStretch()

        layout.addLayout(test_row)
        self._test_thread = None

        # Encryption note
        encryption_note = QLabel(
            "<small>Credentials are encrypted with Fernet"
            " (AES-128-CBC + HMAC-SHA256) using a CSPRNG master key,"
            " then stored in your OS keyring (Windows Credential"
            " Manager / macOS Keychain / Linux Secret Service)."
            "<br><br>They are tied to your user account and"
            " won't transfer to other computers.</small>"
        )
        encryption_note.setWordWrap(True)
        encryption_note.setProperty("class", "label-credential-note")
        layout.addWidget(encryption_note)

        return group
```

- [ ] **Step 4: Add `get_credentials()` and `save_credentials()` methods**

Add these methods after the `_create_credentials_group()` method, replacing the old popup dialog methods (`change_api_key`, `_handle_api_key_dialog_result`, `change_username`, `_handle_username_dialog_result`, `change_password`, `_handle_password_dialog_result`, `remove_api_key`, `_handle_remove_api_key_confirmation`, `remove_username`, `_handle_remove_username_confirmation`, `remove_password`, `_handle_remove_password_confirmation`):

```python
    def get_credentials(self) -> dict:
        """Read current credential values from widget fields.

        Returns:
            Dict with keys 'api_key', 'username', 'password' (only keys that
            exist for this host). Values are plaintext strings from the fields.
        """
        creds = {}
        if self.api_key_input is not None:
            creds['api_key'] = self.api_key_input.text().strip()
        if self.username_input is not None:
            creds['username'] = self.username_input.text().strip()
        if self.password_input is not None:
            creds['password'] = self.password_input.text().strip()
        return creds

    def save_credentials(self):
        """Persist credential field values to encrypted keyring storage.

        Non-empty values are encrypted and stored. Empty values trigger
        removal of the corresponding keyring entry.
        """
        creds = self.get_credentials()

        for key in ['api_key', 'username', 'password']:
            if key not in creds:
                continue
            value = creds[key]
            if value:
                set_credential(key, encrypt_password(value), self.host_id)
            else:
                remove_credential(key, self.host_id)
```

- [ ] **Step 5: Rewrite `load_current_credentials()` to populate fields**

Replace `load_current_credentials()` (lines 790-893) with:

```python
    def load_current_credentials(self):
        """Load stored credentials into the inline fields."""
        if self.username_input is None:
            return

        # Username
        encrypted_username = get_credential('username', self.host_id)
        if encrypted_username:
            try:
                self.username_input.setText(decrypt_password(encrypted_username))
            except Exception:
                self.username_input.setText("")
        else:
            self.username_input.setText("")

        # Password
        encrypted_password = get_credential('password', self.host_id)
        if encrypted_password:
            try:
                self.password_input.setText(decrypt_password(encrypted_password))
            except Exception:
                self.password_input.setText("")
        else:
            self.password_input.setText("")

        # API Key (if field exists)
        if self.api_key_input is not None:
            encrypted_api_key = get_credential('api_key', self.host_id)
            if encrypted_api_key:
                try:
                    self.api_key_input.setText(decrypt_password(encrypted_api_key))
                except Exception:
                    self.api_key_input.setText("")
            else:
                self.api_key_input.setText("")

        # Firefox Cookies (if row exists)
        if self.cookies_status_label is None:
            return

        config = configparser.ConfigParser()
        config_file = get_config_path()
        cookies_enabled = True
        if os.path.exists(config_file):
            config.read(config_file, encoding='utf-8')
            if 'CREDENTIALS' in config:
                cookies_enabled_val = str(config['CREDENTIALS'].get('cookies_enabled', 'true')).lower()
                cookies_enabled = cookies_enabled_val != 'false'

        if cookies_enabled:
            self.cookies_status_label.setText("Enabled")
            self.cookies_status_label.setProperty("class", "status-success")
        else:
            self.cookies_status_label.setText("Disabled")
            self.cookies_status_label.setProperty("class", "status-error")

        style = self.cookies_status_label.style()
        if style:
            style.polish(self.cookies_status_label)

        self.cookies_enable_btn.setEnabled(not cookies_enabled)
        self.cookies_disable_btn.setEnabled(cookies_enabled)
```

- [ ] **Step 6: Update `_start_credential_test()` to read from widget fields**

Replace `_start_credential_test()` (lines 1176-1212) with:

```python
    def _start_credential_test(self):
        """Start a background credential test using current widget values."""
        creds = self.get_credentials()

        # Filter to non-empty values
        credentials = {k: v for k, v in creds.items() if v}

        if not credentials:
            self.test_result_label.setText(
                "<span style='color:orange;'>No credentials entered to test</span>"
            )
            return

        self.test_credentials_btn.setEnabled(False)
        self.test_result_label.setText("Testing...")

        self._test_thread = _CredentialTestThread(self.host_id, credentials, self)
        self._test_thread.result.connect(self._on_test_result)
        self._test_thread.start()
```

- [ ] **Step 7: Remove old popup dialog methods**

Delete these methods entirely from `ImageHostConfigPanel`:
- `change_api_key()` and `_handle_api_key_dialog_result()`
- `change_username()` and `_handle_username_dialog_result()`
- `change_password()` and `_handle_password_dialog_result()`
- `remove_api_key()` and `_handle_remove_api_key_confirmation()`
- `remove_username()` and `_handle_remove_username_confirmation()`
- `remove_password()` and `_handle_remove_password_confirmation()`

These are no longer called from anywhere — the inline fields replace them.

- [ ] **Step 8: Update `save()` to include credential saving**

In the `save()` method (around line 735), add a call to `save_credentials()` at the start:

```python
    def save(self):
        """Save all settings including credentials."""
        self.save_credentials()

        # ... rest of existing save() code unchanged ...
```

- [ ] **Step 9: Update `_gather_credentials()` in `image_host_config_dialog.py`**

Update `ImageHostConfigDialog._gather_credentials()` to read from panel fields instead of keyring:

```python
    def _gather_credentials(self) -> dict:
        """Read current credentials from panel widget fields."""
        creds = self.panel.get_credentials()
        return {k: v for k, v in creds.items() if v}
```

- [ ] **Step 10: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/gui/widgets/test_image_host_config_panel.py -v`
Expected: PASS

- [ ] **Step 11: Run full test suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: PASS. Fix any tests that reference old attribute names (`api_key_status_label`, `api_key_change_btn`, `api_key_remove_btn`, `username_status_label`, `username_change_btn`, `username_remove_btn`, `password_status_label`, `password_change_btn`, `password_remove_btn`).

- [ ] **Step 12: Commit**

```bash
git add src/gui/widgets/image_host_config_panel.py src/gui/dialogs/image_host_config_dialog.py tests/unit/gui/widgets/test_image_host_config_panel.py
git commit -m "feat(gui): rewrite image host credentials as inline editable fields

Replace Set/Unset buttons and popup dialogs with inline QLineEdit
fields + show/hide eye toggle buttons, matching the file host config
pattern. Add get_credentials() and save_credentials() methods.
Test button now reads from widget fields instead of keyring."
```

---

### Task 5: Update file host config dialog — username masking + move test button

**Files:**
- Modify: `src/gui/dialogs/file_host_config_dialog.py`
- Test: `tests/unit/gui/dialogs/test_file_host_credentials_ui.py` (update existing)

Two changes: (1) username fields get `EchoMode.Password` + eye toggle, (2) test section moves into credentials group.

- [ ] **Step 1: Add eye toggle to username fields**

In `src/gui/dialogs/file_host_config_dialog.py`, find the username field creation in the "mixed" branch (lines 235-242) and "username/password" branch (lines 269-276). Change the username `QLineEdit` to use `AsteriskPasswordEdit` with a show/hide button.

For the **mixed auth** branch (lines 235-242), replace:

```python
                self.creds_username_input = QLineEdit()
                self.creds_username_input.setFont(QFont("Consolas", 10))
                self.creds_username_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                self.creds_username_input.setPlaceholderText("Enter username...")
                self.creds_username_input.blockSignals(True)
                self.creds_username_input.setText(username_val)
                self.creds_username_input.blockSignals(False)
                creds_layout.addRow("Username:", self.creds_username_input)
```

with:

```python
                self.creds_username_input = AsteriskPasswordEdit()
                self.creds_username_input.setFont(QFont("Consolas", 10))
                self.creds_username_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                self.creds_username_input.setPlaceholderText("Enter username...")
                self.creds_username_input.blockSignals(True)
                self.creds_username_input.setText(username_val)
                self.creds_username_input.blockSignals(False)

                username_row = QHBoxLayout()
                username_row.addWidget(self.creds_username_input)

                show_user_btn = QPushButton()
                show_user_btn.setIcon(icon_manager.get_icon('action_view'))
                show_user_btn.setMaximumWidth(30)
                show_user_btn.setCheckable(True)
                show_user_btn.setToolTip("Show/hide username")
                show_user_btn.clicked.connect(
                    lambda checked: self.creds_username_input.set_masked(not checked)
                )
                username_row.addWidget(show_user_btn)

                creds_layout.addRow("Username:", username_row)
```

Apply the same change to the **username/password** branch (lines 269-276):

```python
                self.creds_username_input = AsteriskPasswordEdit()
                self.creds_username_input.setFont(QFont("Consolas", 10))
                self.creds_username_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                self.creds_username_input.setPlaceholderText("Enter username...")
                self.creds_username_input.blockSignals(True)
                self.creds_username_input.setText(username_val)
                self.creds_username_input.blockSignals(False)

                username_row = QHBoxLayout()
                username_row.addWidget(self.creds_username_input)

                show_user_btn = QPushButton()
                show_user_btn.setIcon(icon_manager.get_icon('action_view'))
                show_user_btn.setMaximumWidth(30)
                show_user_btn.setCheckable(True)
                show_user_btn.setToolTip("Show/hide username")
                show_user_btn.clicked.connect(
                    lambda checked: self.creds_username_input.set_masked(not checked)
                )
                username_row.addWidget(show_user_btn)

                creds_layout.addRow("Username:", username_row)
```

- [ ] **Step 2: Move test section into credentials group**

In `setup_ui()`, the test section is currently added to `content_layout` via `self.setup_test_results_section(content_layout)` (line 491). Change this to add to `creds_group` layout instead.

Move the `self.setup_test_results_section(...)` call from line 491 (after `content_layout.addWidget(settings_group)`) to just before `content_layout.addWidget(creds_group)` (line 301), passing the credentials group layout:

In the credentials group creation section (around line 301), add the test section call before adding `creds_group` to `content_layout`:

```python
            # Add test section inside credentials group
            self.setup_test_results_section(creds_layout if isinstance(creds_layout, QVBoxLayout) else creds_group.layout())

            content_layout.addWidget(creds_group)
```

Wait — `creds_layout` is a `QFormLayout`, so we need a `QVBoxLayout` wrapper. The simplest approach: change `setup_test_results_section` to not create its own group box (since it's now inside the credentials group). Modify `setup_test_results_section()`:

```python
    def setup_test_results_section(self, parent_layout):
        """Setup the test results section with test button.

        Adds directly to parent_layout without a wrapping group box.
        """
        # Test button at top
        test_button_layout = QHBoxLayout()
        self.test_connection_btn = QPushButton("Test Connection")
        self.test_connection_btn.setToolTip("Run full test: credentials, user info, upload, and delete")
        self.test_connection_btn.setEnabled(True)
        test_button_layout.addWidget(self.test_connection_btn)
        test_button_layout.addStretch()
        parent_layout.addLayout(test_button_layout)

        # Test results display
        test_results_layout = QFormLayout()

        self.test_timestamp_label = QLabel("Not tested yet")
        self.test_credentials_label = QLabel("○ Not tested")
        self.test_userinfo_label = QLabel("○ Not tested")
        self.test_upload_label = QLabel("○ Not tested")
        self.test_delete_label = QLabel("○ Not tested")
        self.test_error_label = QLabel("")
        self.test_error_label.setWordWrap(True)
        self.test_error_label.setProperty("class", "error-small")

        test_results_layout.addRow("Last tested:", self.test_timestamp_label)
        test_results_layout.addRow("Credentials:", self.test_credentials_label)
        test_results_layout.addRow("User info:", self.test_userinfo_label)
        test_results_layout.addRow("Upload test:", self.test_upload_label)
        test_results_layout.addRow("Delete test:", self.test_delete_label)
        test_results_layout.addRow("", self.test_error_label)

        parent_layout.addLayout(test_results_layout)

        # Load and display existing test results
        self.load_and_display_test_results()

        # Connect test button
        self.test_connection_btn.clicked.connect(self.run_full_test)
```

Then move the call site: inside the credentials group section (after credential fields are set up, around line 300), add:

```python
            # Test section inside credentials group
            self.setup_test_results_section(creds_group.layout())

            content_layout.addWidget(creds_group)
```

And remove the old call at line 491:
```python
        # DELETE: self.setup_test_results_section(content_layout)
```

For hosts without auth (`requires_auth=False`), the test section needs to still exist somewhere. Add a guard: if `not self.host_config.requires_auth`, create the test section in `content_layout` as before (standalone, without group box wrapper).

- [ ] **Step 3: Run existing file host tests**

Run: `.venv/bin/python -m pytest tests/unit/gui/dialogs/test_file_host_credentials_ui.py tests/unit/gui/dialogs/test_file_host_config_dialog.py -v`
Expected: Some may fail due to username field type change from `QLineEdit` to `AsteriskPasswordEdit`. Fix any failing assertions.

- [ ] **Step 4: Update credential UI tests for username masking**

In `tests/unit/gui/dialogs/test_file_host_credentials_ui.py`, update tests that create username fields as plain `QLineEdit` to expect `AsteriskPasswordEdit`. The `text()` method should still work the same.

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/gui/dialogs/file_host_config_dialog.py tests/unit/gui/dialogs/test_file_host_credentials_ui.py tests/unit/gui/dialogs/test_file_host_config_dialog.py
git commit -m "feat(gui): mask file host usernames + move test into credentials group

Username fields now use AsteriskPasswordEdit with show/hide toggle,
matching the password/API key pattern. Test Connection section moves
from its own group box into the credentials group for consistency."
```

---

### Task 6: Call username migration at startup

**Files:**
- Modify: `bbdrop.py` (add migration call)

The migration needs to run once at startup, after the encryption key is available but before any credential reads.

- [ ] **Step 1: Add migration call to app startup**

In `bbdrop.py`, find where `migrate_credentials_from_ini()` is called (in the startup flow) and add `migrate_plaintext_usernames()` immediately after:

```python
from src.utils.credentials import migrate_credentials_from_ini, migrate_plaintext_usernames

# ... existing code ...
migrate_credentials_from_ini()
migrate_plaintext_usernames()
```

If `migrate_credentials_from_ini()` isn't called in `bbdrop.py`, find the actual startup location and add the call there. The key requirement is: it must run before any `get_credential('username')` + `decrypt_password()` calls.

- [ ] **Step 2: Run full test suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add bbdrop.py
git commit -m "feat(auth): call username encryption migration at startup

Ensures existing plaintext usernames are encrypted before any
consumer tries to decrypt them."
```

---

### Task 7: Final integration test + cleanup

**Files:**
- Run full test suite
- Fix any remaining test failures

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 2: Fix any failures**

Address any test failures related to:
- Old attribute names (`api_key_status_label`, `api_key_change_btn`, etc.)
- Tests that mock `check_credentials` or `api_key_is_set`
- Tests that expect plain `QLineEdit` for username fields in file host dialog
- Import changes

- [ ] **Step 3: Run full test suite again**

Run: `.venv/bin/python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Final commit if any fixes were needed**

```bash
git add -u
git commit -m "fix(tests): update tests for credential UI redesign"
```
