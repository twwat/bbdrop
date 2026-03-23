# ADR-001: pycurl over requests for upload clients

**Status:** Accepted
**Date:** 2025-01-15

## Context

BBDrop uploads files to 10+ image and file hosts through concurrent worker
threads. The upload pipeline needs:

- Real-time bandwidth tracking (bytes sent per chunk, not just per request).
- Bandwidth limiting so uploads don't saturate the user's connection.
- Persistent TCP/TLS connections reused across uploads to the same host.
- Thread-safe concurrent uploads with per-thread connection handles.
- Direct control over SSL verification, timeouts, and proxy settings on every
  request.

Python's `requests` library is the standard choice for HTTP, but it doesn't
expose the low-level callbacks and connection controls listed above. libcurl
(via `pycurl`) does.

At the same time, IMX.to --- the first host BBDrop supported --- has a simple
JSON REST API where `requests` works well and was already in place before the
multi-host architecture existed.

## Decision

Use **pycurl** for all upload clients except IMX.to, which continues to use
**requests**.

### Why pycurl

pycurl exposes libcurl options that `requests` cannot provide:

- **`CURLOPT_XFERINFOFUNCTION`** --- progress callback invoked during data
  transfer, reporting bytes sent per chunk. This drives the real-time speed
  display and per-gallery progress bars.
- **`CURLOPT_MAX_SEND_SPEED_LARGE`** --- server-side-enforced bandwidth cap
  without application-level throttling.
- **Persistent connections** --- calling `curl.reset()` clears options but keeps
  the underlying TCP+TLS connection alive, giving connection reuse without a
  session abstraction.
- **Thread-local handles** --- each upload thread stores its own `pycurl.Curl`
  instance in `threading.local()`, providing thread safety and per-thread
  connection pooling without shared state.
- **Per-request control** --- SSL verification, connect/read timeouts, proxy
  configuration (HTTP, SOCKS4, SOCKS5), and custom headers are set on each
  handle before `perform()`.

All three pycurl-based image host clients (`TurboImageHostClient`,
`PixhostClient`) and the `FileHostClient` (covering 7 file hosts) follow this
pattern. Each creates thread-local curl handles via `_get_thread_curl()` and
reuses them across uploads within a gallery.

### Why requests for IMX.to

`ImxToUploader` in `bbdrop.py` uses `requests` because:

- IMX.to's API is a straightforward JSON REST endpoint ---
  `requests.post()` with a file and JSON parsing is all that's needed.
- `requests` was already in use before the multi-host architecture was designed.
- The IMX API returns the normalized response shape natively
  (`{status, data: {image_url, thumb_url, gallery_id}}`), so no low-level
  response parsing is required.

## Consequences

**Positive:**

- Fine-grained bandwidth tracking powers the GUI speed display and per-gallery
  progress without polling.
- Connection reuse reduces TLS handshake overhead on bulk uploads (50--500
  images per gallery).
- Thread-local handles keep concurrent uploads isolated without locks on the
  HTTP layer.

**Negative:**

- pycurl requires `libcurl` development headers at build time, complicating
  installation from source on some platforms.
- The pycurl API is more verbose than `requests` --- each call requires manual
  option setting, buffer management, and error handling.
- pycurl handles are harder to mock in unit tests compared to
  `requests.Session`.

**Tradeoff:**

- Two HTTP libraries coexist in the codebase (`requests` for IMX, `pycurl` for
  everything else). This adds a small maintenance cost, but each library is used
  where its strengths apply. Replacing `requests` for IMX would add complexity
  without benefit; replacing `pycurl` everywhere else would sacrifice bandwidth
  tracking and connection control.
