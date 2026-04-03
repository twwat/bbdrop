# Credential UI Redesign

## Summary

Three changes to credential handling:

1. Remove the IMX-specific startup credential check
2. Replace image host credential widgets (Set/Unset buttons + status labels + popup dialogs) with inline editable fields matching the file host pattern
3. Move Test buttons into the credentials group for both image and file hosts

Functional changes: removing the startup check, and encrypting usernames. Everything else is GUI/interface changes only.

## 1. Remove IMX-Specific Startup Credential Check

### What to remove

- `has_imx_credentials()` helper function (`main_window.py:215-225`)
- `api_key_is_set()` helper function (`main_window.py:227-233`)
- `check_credentials()` method (`main_window.py:2302-2309`)
- The `self.check_credentials()` call in `BBDropGUI.__init__()` (`main_window.py:889`)

### What stays

Existing startup checks for other enabled hosts (file host spinup, etc.) are untouched.

## 2. Image Host Credentials: Inline Editable Fields

### Current pattern (remove)

Each credential field has:
- A read-only status label ("API Key: Set", "NOT SET", "Logged in as {username}")
- Set button (opens input dialog)
- Unset button (clears stored value)
- Separate show/hide toggle (API key only)

### New pattern (match file host config)

Each credential field becomes:
- `QLineEdit` with `EchoMode.Password` (masked by default)
- Eye toggle button to switch between `EchoMode.Password` and `EchoMode.Normal`
- Fields load stored/decrypted values on dialog open
- Fields save on OK/Apply (same lifecycle as file host dialog)

### Per-host field layout

**IMX.to** (`auth_type: "api_key"`):
- API Key field (masked + eye toggle)
- Username field (masked + eye toggle)
- Password field (masked + eye toggle)
- Firefox Cookies toggle (unchanged)

**TurboImageHost** (`auth_type: "optional_session"`):
- Username field (masked + eye toggle)
- Password field (masked + eye toggle)
- Optional credentials notice (unchanged)

**Pixhost** (`auth_type: "none"`):
- No credential fields (unchanged)

### What doesn't change

- Credential storage/encryption (Fernet + keyring)
- Per-host branching logic (which fields appear for which host)
- Firefox cookies toggle behavior for IMX
- The encrypted storage note at the bottom

## 3. File Host Credentials: Username Fields Get Eye Toggle

Currently file host username fields are plain `QLineEdit` (unmasked). For consistency, all credential fields — including usernames — get `EchoMode.Password` + eye toggle in both image and file host config.

## 4. Move Test Buttons Into Credentials Group

### Image hosts

Move the existing "Test Credentials" button from its current position into the credentials group box, directly below the credential fields. Test logic and result display unchanged.

### File hosts

Move the existing "Test Connection" button (and its results display) out of the separate "Connection Test (optional)" group box and into the credentials group box. Remove the now-empty group box. Test logic, threading, result caching, and checklist display unchanged.

## Files Affected

| File | Change |
|------|--------|
| `src/gui/main_window.py` | Remove `check_credentials()`, `check_stored_credentials()`, `api_key_is_set()` and the `__init__` call |
| `src/gui/widgets/image_host_config_panel.py` | Replace Set/Unset buttons + status labels with inline `QLineEdit` fields + eye toggles; move Test button into credentials group; encrypt/decrypt usernames |
| `src/gui/dialogs/file_host_config_dialog.py` | Add eye toggle to username fields; move Test Connection button/results into credentials group; encrypt/decrypt usernames |
| `src/utils/credentials.py` | Add migration for plaintext usernames → encrypted |
| `src/network/imx_uploader.py` | Decrypt username in `_get_credentials()` |
| `src/processing/rename_worker.py` | Decrypt username on read |
| `src/processing/scan_coordinator.py` | Decrypt username on read in `_load_file_host_credentials()` |

## 5. Encrypt Usernames

Currently usernames are stored plaintext in keyring while passwords and API keys are Fernet-encrypted. Since all credential fields are now masked by default in the UI, encrypt usernames the same way — `encrypt_password()` on save, `decrypt_password()` on read.

This affects every code path that reads or writes usernames:

- **`src/utils/credentials.py`**: `get_credential()` / `set_credential()` calls for username keys — wrap with encrypt/decrypt
- **`src/network/imx_uploader.py`**: `_get_credentials()` — decrypt username on read
- **`src/gui/widgets/image_host_config_panel.py`**: credential save/load — encrypt username on save, decrypt on load
- **`src/gui/dialogs/file_host_config_dialog.py`**: credential save/load — encrypt username on save, decrypt on load
- **`src/processing/rename_worker.py`**: `get_credential('username')` — decrypt on read
- **`src/processing/scan_coordinator.py`**: `_load_file_host_credentials()` — decrypt username on read

Existing plaintext usernames in keyring need a one-time migration: read plaintext, re-store as encrypted. This can piggyback on the existing `_migrate_encryption_keys()` pattern.

## Out of Scope

- Credential storage changes beyond username encryption
- Test logic or threading changes
- New hosts or auth types
- Settings tab layout changes (the per-host rows with Configure buttons)
- File host spinup/startup behavior
