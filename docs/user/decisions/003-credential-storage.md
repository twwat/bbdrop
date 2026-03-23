# ADR-003: Fernet encryption with OS keyring

**Status:** Accepted
**Date:** 2025-01-15

## Context

BBDrop stores credentials for 10+ hosts: API keys (IMX.to, RapidGator),
username/password pairs (TurboImageHost, Keep2Share, FileBoom, TezFiles,
Filedot, Filespace, Katfile), and proxy passwords. These credentials must be:

- **Encrypted at rest** --- plaintext credentials in config files are
  unacceptable.
- **Retrievable without user interaction** --- the application must decrypt
  credentials on launch without prompting for a master password.
- **Portable across platforms** --- Windows, macOS, and Linux.

An earlier implementation derived the encryption key from `SHA-256(username +
hostname)`, which was predictable and offered no real security. The system
needed a proper cryptographic key stored in platform-native secure storage.

## Decision

Use a **two-layer encryption scheme**:

1. **Fernet encryption** (AES-128-CBC + HMAC-SHA256) for all credential values.
   The `cryptography` library's `Fernet` class provides authenticated
   encryption --- each ciphertext includes an HMAC that detects tampering.

2. **CSPRNG master key stored in the OS keyring.** On first run, the
   `generate_fernet_key()` function in `src/utils/credential_helpers.py`
   generates a 256-bit key using `secrets.token_bytes(32)` (backed by the OS
   cryptographic RNG: `/dev/urandom` on Linux, `CryptGenRandom` on Windows).
   This key is base64url-encoded for Fernet compatibility and stored in the OS
   keyring under the service name `"bbdrop"` with the key `"_master_key"`.

3. **Platform keyring backends:**
   - Windows: Windows Credential Manager
   - macOS: macOS Keychain
   - Linux: Secret Service API (requires D-Bus and a provider like
     GNOME Keyring or KDE Wallet)

### Storage layout

- **Encrypted credential blobs** are stored in the OS keyring under
  service `"bbdrop"` with keys like `file_host_rapidgator_credentials`,
  `imx_password`, or `turbo_api_key`. The blobs are opaque Fernet tokens.
- **Plaintext metadata** (usernames) is also stored in the keyring but not
  encrypted, since usernames are not secrets.
- **The master key** is a single keyring entry (`_master_key`) that unlocks all
  other credentials.

### Authentication methods

Auth methods vary by host --- API key, token-based login, session-based login
--- but the credential storage mechanism is the same for all. Session cookies
are auth artifacts obtained from credentials, not credentials themselves; they
are cached in memory with TTL-based expiration, not persisted as credentials.

### Migration

A one-time migration (`_migrate_encryption_keys()` in `src/utils/credentials.py`)
runs on the first launch after upgrading from the legacy SHA-256-derived key.
It reads all existing credentials from the keyring (and QSettings as a final
fallback), decrypts them with the old key, re-encrypts with the new CSPRNG key,
and stores the new master key. QSettings credential entries are removed after
migration.

## Consequences

**Positive:**

- AES encryption with HMAC integrity verification --- tampered ciphertext is
  detected and rejected.
- The master key lives in platform-native secure storage that's unlocked when
  the user logs in to their OS account. On modern hardware (Windows with TPM,
  macOS with Secure Enclave), the keyring is hardware-backed.
- No plaintext credentials anywhere --- not in INI files, not in QSettings, not
  in environment variables.
- Automatic migration path from the legacy insecure scheme.

**Negative:**

- Depends on OS keyring availability. On Linux, this requires the Secret
  Service D-Bus API, which may not be present in headless or minimal
  environments.
- There is **no fallback** if the keyring is unavailable. This is deliberate: an
  insecure fallback (e.g., storing the key in QSettings or a plaintext file)
  would undermine the entire encryption model. If the keyring is missing,
  `CredentialDecryptionError` is raised and the user must configure a keyring
  backend.

**Tradeoff:**

- If the keyring is unavailable or wiped, credentials can't be decrypted and
  the user must re-enter them. This prioritizes security over convenience --- a
  credential store that silently degrades to plaintext is worse than one that
  fails loudly.
