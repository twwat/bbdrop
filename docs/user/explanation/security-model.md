# Security Model

BBDrop handles credentials for up to 10 different hosting services. This document explains the layered security architecture that protects those credentials at rest, in transit, and in memory.

## Authentication methods

Different hosts use different authentication mechanisms. These are host-imposed requirements, not choices BBDrop makes:

- **API key auth** -- The host issues a permanent API key. BBDrop stores it encrypted and sends it with each request. No login step is needed. (Example: IMX.to API key mode.)
- **Token-based login** -- BBDrop sends a username and password to the host's login endpoint and receives a session token. The token is cached (encrypted) with a configurable TTL and refreshed automatically when it expires. (Example: RapidGator, Keep2Share.)
- **Session-based login** -- BBDrop posts credentials to a login form and receives session cookies. The cookies are reused across uploads within the same session. (Example: Filedot, Filespace.)

In all three cases, the underlying credential (API key or username/password pair) is stored using the same encryption layer described below. Session cookies and tokens are auth artifacts obtained from credentials -- they are cached for performance but regenerated when they expire.

## Credential storage

### Encryption

BBDrop encrypts sensitive credentials using [Fernet](https://cryptography.io/en/latest/fernet/) symmetric encryption, which combines AES-128-CBC for confidentiality with HMAC-SHA256 for integrity. A single master key protects all credentials.

The encryption flow works as follows:

1. **Master key generation** -- On first run, BBDrop generates a 256-bit master key using the OS cryptographic random number generator (`secrets.token_bytes(32)`). This is a CSPRNG (cryptographically secure pseudorandom number generator) -- not derived from any predictable input.
2. **Master key storage** -- The master key is stored in the OS keyring: Windows Credential Manager, macOS Keychain, or Linux Secret Service (via D-Bus). The master key never touches disk in plaintext.
3. **Credential encryption** -- When you save a password, BBDrop encrypts it with `Fernet(master_key).encrypt()` and stores the encrypted blob in the OS keyring alongside the master key.
4. **Credential decryption** -- When a credential is needed, BBDrop retrieves the master key from the keyring, then decrypts the credential blob. The master key is cached in process memory after first access (protected by a threading lock for thread safety).

### Why the OS keyring

The OS keyring provides hardware-backed or user-session-scoped protection depending on the platform:

- **Windows Credential Manager** -- Encrypted with the user's login credentials via DPAPI. Other user accounts on the same machine cannot read the stored keys.
- **macOS Keychain** -- Protected by the user's login keychain, which is locked when the user logs out.
- **Linux Secret Service** -- Typically backed by GNOME Keyring or KDE Wallet, encrypted with the user's session credentials.

Storing the master key in the keyring means an attacker who obtains the encrypted credential blobs (for example, from a backup) cannot decrypt them without also compromising the OS user session.

### Legacy migration

Older versions of BBDrop derived the encryption key from `SHA-256(username + hostname)`, which is predictable. On first run after upgrade, BBDrop performs a one-time migration: it decrypts all existing credentials with the old key, re-encrypts them with a fresh CSPRNG key, stores the new key in the OS keyring, and removes credentials from QSettings. This migration is automatic and transparent.

## Transport security

All HTTP connections use TLS 1.2 or later with certificate verification:

- **requests** (used by IMX.to) -- Verifies certificates against the `certifi` CA bundle by default.
- **pycurl** (used by TurboImageHost, Pixhost, and all file hosts) -- Explicitly configured with `SSL_VERIFYPEER=1`, `SSL_VERIFYHOST=2`, and `CAINFO` pointing to the `certifi` CA bundle.

Certificate verification is not optional or configurable. Every outbound connection validates the server's certificate chain.

## Token caching

File hosts that use token-based authentication benefit from token caching to avoid repeated login requests. The `TokenCache` stores tokens with these properties:

- **Encryption at rest** -- Tokens are encrypted with the same Fernet master key used for credentials before writing to QSettings.
- **Configurable TTL** -- Each token has an optional time-to-live. When `get_token()` finds an expired token, it clears the cache and returns `None`, triggering a fresh login.
- **Automatic refresh** -- The file host client checks token validity before each upload. If the token has expired or is about to expire, the client re-authenticates and updates the cache.
- **Cache metadata** -- Each token stores `cached_at` and `expires_at` timestamps for diagnostic purposes.

## Database security

The SQLite database (`~/.bbdrop/bbdrop.db`) stores queue state, gallery metadata, and upload results. It does not store credentials (those live in the OS keyring). The database uses these protective measures:

- **Parameterized queries** -- All SQL statements use parameter binding (`?` placeholders), preventing SQL injection regardless of input content.
- **WAL mode** -- Write-Ahead Logging allows concurrent readers during writes, reducing lock contention. This is a reliability feature, but it also prevents reader threads from seeing partially written transactions.
- **Column whitelist** -- Dynamic column references (for sorting and filtering) are validated against a whitelist of known column names. This prevents injection through column name parameters, which cannot use parameterized binding.
- **SQL wildcard escaping** -- User-provided search strings are escaped for SQL LIKE patterns to prevent unintended wildcard matching.

## Thread safety

BBDrop runs upload operations across multiple threads: the GUI thread, upload worker threads, file host worker threads, rename workers, scan workers, and bandwidth polling threads. Shared state is protected by:

- **QMutex** -- The `QueueManager` uses a Qt mutex to protect the items dictionary from concurrent modification by the GUI thread and worker threads.
- **threading.Lock** -- The `AtomicCounter` for bandwidth tracking, the master key cache, and per-host connection state each use Python threading locks.
- **Thread-local storage** -- pycurl handles are stored in `threading.local()` so each thread gets its own TCP connection without lock contention.

## Timing attack prevention

Password comparison uses `secrets.compare_digest()` instead of Python's `==` operator. The `==` operator for strings short-circuits on the first mismatched character, which leaks information about how many leading characters are correct. `compare_digest()` runs in constant time regardless of where the strings differ.

## Input validation

- **Path normalization** -- File paths are normalized with `os.path.normpath()` to resolve `.` and `..` segments before use, preventing path traversal.
- **Gallery name sanitization** -- Each host's `sanitize_gallery_name()` strips control characters and enforces host-specific length and character restrictions.
- **File size limits** -- The upload engine checks files against the host's configured `max_file_size_mb` before uploading, preventing wasted bandwidth on files the host would reject.

---

Back to [Explanation](./index.md)
