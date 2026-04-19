# Changelog

All notable changes to BBDrop will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.9.8] - 2026-04-19 ([full changelog](https://github.com/twwat/bbdrop/compare/v0.9.7...v0.9.8))

### Added
- **File Manager persistent cache**: File list cache now survives across sessions via SQLite, with configurable TTL in **Settings → Advanced**
  - Cache entries keyed by host and pagination state for accurate resumption
  - Galleries linked via file_host_uploads table; file list displays Gallery, Downloads, and Last DL columns
  - Loading feedback ("Loading…") shown in tree and file list during refresh
- **K2S family shared storage display**: Keep2Share, FileBoom, and TezFiles now display shared 10 TiB quota across all three hosts, matching the host's UI
  - Clickable storage bar in **File Hosts** tab and worker status panel opens quota editor for quick adjustment
  - Daily traffic line visible in storage bar tooltip for bandwidth monitoring
  - Storage usage auto-updates on scan completion and file host uploads
- **Contact Sheets tab (renamed from Video)**: Video settings tab renamed for clarity and redesigned with two-column grid layout
  - Video template placeholders added to syntax highlighter
  - Infobuttons reorganised for better navigation
- **BBCode link format editor**: Customisable format string for file host download links accessible via file host config dialog
  - `#fileSize#` placeholder now available in file host link templates for including file sizes in BBCode
  - PlaceholderEditorDialog supports all format, link, and metadata placeholders with live syntax highlighting
- **Customisable dock layout**: Save and restore window panel layouts via View menu
  - Preset layouts selectable from View menu
  - **Edit Layout** mode to unlock docks for rearrangement; a compact drag handle replaces the dock title bar when unlocked
  - Reset Layout entry to restore defaults
  - Layout persists across sessions via `saveState`/`restoreState`
- **Settings menu**: All 13 settings tabs now accessible directly from the **Settings** menu

### Changed
- **Worker table speed + status columns combined**: Speed and status text now share a single column for a tighter layout; hiding this column is respected across restarts
- **File Manager for video galleries**: Manage Files menu item no longer appears for video queue entries
- **K2S upload access**: K2S family uploads now explicitly set `access=public` by default
- **Post Title template field**: Templates gain a per-template Post Title with `#galleryName#` and `#galleryTitle#` support; BBCode regeneration and notifications debounced during file host upload bursts
- **Worker table filter alignment**: Filter button stays aligned regardless of columns; icon column is non-clickable
- **Quieter logs**: Routine settings-save, startup-complete, and rename-worker auth-success logs demoted to debug

### Fixed
- **Theme toggle preserves storage bar**: Traffic/storage bar accent is re-applied after a theme switch so the display no longer reverts
- **Screenshot sheet metadata**: FPS, bitrate, and audio track info now formatted correctly on the screenshot sheet overlay
- **File Manager trash pagination**: Page state is preserved when browsing the trash view
- **File Manager token refresh**: RapidGator refreshes the session token on "Session doesn't exist" instead of failing
- **File Manager domain selection**: K2S Copy Link uses the correct domain per host (K2S, FileBoom, or TezFiles)
- **File Manager folder errors**: Failed folder fetches now surface visibly in the tree instead of failing silently
- **File Manager file navigation**: Clicking a file opens that file's page, not `/myfiles`
- **File Manager disabled host**: Switching to a disabled file host no longer crashes
- **File Manager folder tree**: `..` entries no longer appear in the folder tree
- **File Manager gallery column**: Gallery column is populated correctly on cached file-list renders
- **File Manager session cleanup**: Stale session references are evicted when a file host worker is disabled
- **K2S / RapidGator upload retry**: Resolved an UnboundLocalError on upload retry
- **Startup progress bar**: Progress bar now seeds from the combined byte-weighted percent on queue load instead of snapping
- **UTF-8 INI handling**: All INI file read/write paths now enforce UTF-8 so non-ASCII values round-trip correctly
- **Scanner robustness**: K2S inventory cache is thread-safe; missing inventory files are treated as offline rather than errors; K2S storage is written back on scan completion and incremented thread-safely during uploads
- **Dock layout polish**: Bottom docks no longer lump or cascade on resize; Reset Layout always works; `View Panels` toggles work in locked mode; dock title-bar cursor, tooltips, and button sizing corrected

## [0.9.7] - 2026-04-15 ([full changelog](https://github.com/twwat/bbdrop/compare/v0.9.6...v0.9.7))

### Added
- **K2S family dedup**: Keep2Share, FileBoom, and TezFiles share the same storage backend, so uploading the same file to multiple of these hosts now deduplicates server-side instead of re-uploading
  - `HostFamilyCoordinator` mirrors a successful upload to its sibling hosts via the shared backend's hash API
  - Server MD5 fetched on the primary upload to enable sibling matching
  - Retry with exponential backoff if the dedup hash isn't yet visible to siblings
  - Bytes saved tracked in a `bytes_saved` metric and rolled into file host stats
  - Toggle in **Settings → Advanced → K2S family dedup**
  - Status bar notification on dedup completion
  - File host upload rows render a "blocked" state with a tooltip explaining which sibling the gallery is waiting on
- **Video sheet hover preview**: Hover the film-reel icon in the queue table's Type column to see a scaled tooltip preview of the screenshot sheet; click to open the full preview dialog
  - **Hover preview width** setting in **Settings → Video → Sheet** controls the tooltip image size (200–1920 px, default 640 px)
- **Byte-weighted per-row progress bars**: Each queue row's progress bar now reflects total upload work (image host + file host bytes) instead of image-count progress, so a multi-GB file host upload no longer snaps the row to 100% the moment the image host finishes
  - Cancelled and blocked file host rows are excluded from the work calculation, so abandoned uploads don't strand a gallery at "uploading" forever
- **Browse Files context menu and button**: Open the File Manager directly from a file host's right-click context menu and from the file host config dialog
- **File host upload stats**: Uploaded, skipped, and total bytes per host (with dedup savings reflected in skipped)

### Changed
- **Byte-weighted overall progress bar**: The main queue progress bar uses byte-weighted math across all queued galleries, with delayed completion notification so the bar settles before "queue finished" fires
- **Video gallery size accounting**: Queue size column shows the screenshot sheet size (the file actually uploaded to image hosts) while the underlying video file size drives file host transfer accounting
- **Screenshot sheet reuse**: Video uploads now reuse the screenshot sheet generated at scan time instead of regenerating it
- **Tooltip cache hardening**: Hover preview cache files embed the source mtime in the filename so a regenerated screenshot sheet always produces a fresh preview
- **Video screenshot memory use**: Frames are downscaled before buffering, cutting peak RAM during screenshot sheet generation for long source videos
- **Release installer slimmed**: Dev-only documentation (architecture notes, signal flow diagrams, API references) is no longer bundled; the in-app Help dialog still reads user-facing docs shipped in `docs/user/`
- Reduced log verbosity across the upload pipeline

### Fixed
- **Non-ASCII upload filenames**: pycurl `FORM_FILE` paths are now encoded as bytes, so uploads of files with accented or non-Latin characters no longer fail
- **Single-file video manual upload**: Manual "Upload to file host" now works for single-file video galleries
- **Video BBCode and artifacts**: BBCode and artifact generation for video galleries no longer require a gallery ID
- **Failed file host workers**: Failed workers now show a retry action so you can recover without restarting the host
- **File host queue display**: Manually adding or removing items from a file host queue now refreshes the display immediately
- **Blocked status cleanup**: Blocked file host uploads can now be cancelled or disabled cleanly (previously only `pending` rows were handled)
- **File host byte persistence**: Source byte counts persist correctly on insert, fixing stale numbers in the upload stats
- **Help dialog broken entries**: "File Hosts" and "BBCode Templates" entries in the Help dialog no longer fail with "file not found" — they now point at the actual guides
- **Settings dialog geometry**: The Settings window resets to a valid size if a previously saved geometry was oversized or off-screen
- **File host storage bar width**: The storage usage bar in the File Hosts tab no longer forces its column wider than needed
- **Advanced settings checkbox alignment**: Boolean toggles in the Advanced settings table are now centred consistently in their column

## [0.9.6] - 2026-04-12 ([full changelog](https://github.com/twwat/bbdrop/compare/v0.9.5...v0.9.6))

### Added
- **File Manager**: In-app file browser for remote file hosts, accessible via Tools → File Manager
  - Supports K2S/FileBoom/TezFiles (JSON API), RapidGator (JSON API with trash and copy), Katfile (XFS REST), Filespace (XFS + web scraping), and Filedot (web scraping)
  - Folder tree with lazy loading, sortable file list with pagination, drag-and-drop move
  - Per-host capabilities: rename, move, copy, delete, trash, remote upload, file properties
  - Filedot: full CRUD, properties dialog with single and multi-file diff view, flag toggles
  - Quick settings panel button for fast access
- **Video settings tab redesign**: Complete overhaul with live preview and modern controls
  - Inline preview thumbnail with pop-out to a zoomable full-size window
  - Live preview updates as you tweak settings (debounced)
  - Color pickers for font and background colour (QColorDialog + hex input)
  - JPG now the default output format with quality control merged onto the same row as Format (grayed out when PNG is selected)
  - Tab description and infobuttons on every group, matching other settings tabs
  - Grid/timestamp/appearance settings reorganised for intuitive access
- **Video pipeline refinements**: Built on top of the 0.9.5 video foundation
  - Screenshot sheets generated at scan time instead of on demand
  - Video files added via drag-and-drop and queue browse
  - Video-specific default template and image host override wired through
  - Dedicated Video BBCode template with `#screenshotSheet#`, `#videoDetails#`, video metadata placeholders
  - Actual video frame numbers in timestamp overlay (was using grid index)
  - Video overlay template now resolves all placeholders from formatted metadata
  - Media type column in the queue table
- **Credential UI redesign**: Usernames now encrypted in the OS keyring alongside passwords
  - Inline editable credential fields on image host settings panels
  - Automatic migration of existing plaintext usernames on startup
  - Masked file host usernames with click-to-reveal
  - Descriptive credential labels and security notes across all host settings
- **Settings UI improvements**: Image host thumbnail sliders replaced with spinboxes, upload settings added, infobuttons on all host config panels, unified retry row for file hosts, connection test results moved to a dedicated dialog
- **File host config defaults**: Auto-retry, max upload time, max file size, and connect timeout now have configurable defaults per host

### Changed
- Chrome user-agent consolidated to a single constant in `core/constants.py`

### Fixed
- **K2S upload speed**: Force HTTP/1.1 for Keep2Share/TezFiles/FileBoom uploads — libcurl auto-negotiates HTTP/2 via ALPN but the `filestore.app` CDN throttles HTTP/2 via flow control to ~0.5 MB/s. Forcing HTTP/1.1 restores full throughput (~2x faster). Scoped to K2S family only; other hosts unchanged
- **K2S Cloudflare block**: Added Chrome User-Agent to `createFileByHash` and upload-init pycurl handles. Without it, Cloudflare returned error 1010 with a non-JSON HTML page, showing up as `invalid JSON response` → `HTTP 403 error code: 1010` and immediately failing uploads
- **IMX credential migration**: Unified IMX credential keys to the `imx_`-prefixed format used by other hosts; migrates bare keys on startup and deletes the old entries, removes plaintext fallbacks
- **File Manager API handling**: Corrected K2S and RapidGator response parsing to match the actual API docs
- **File Manager sessions**: Rebuilt session references before the capabilities cache hit; per-host session client routing for Filedot and Filespace; dialog init order and storage display consistency
- **File Manager HTML parsing**: Fixed variable shadowing in page HTML extraction and unescaped HTML entities
- **File Manager Cloudflare bypass**: File manager pycurl clients now send Chrome UA to avoid Cloudflare challenges
- **Auth timing**: Credentials checked at upload time instead of startup — no more noisy logs or false failures when hosts are unconfigured
- **File host connect_timeout**: Setting can now be saved correctly
- **Video single-file uploads**: Single-file video uploads to file hosts now work correctly; artifact save fix for video galleries
- **Video settings persistence**: Stale video settings from pre-0.9.6 preview iterations are reset on upgrade
- **Database**: Restored `tab_name` column that had been dropped by migration 12
- **GUI polish**: Infobutton placement next to labels (not far right) across all settings tabs, infobutton crash fix, video tab false dirty state, grid group alignment, HTML entity handling, layout and consistency fixes across settings dialogs
- **Screenshot sheet preview**: Zoom-to-fit now defers to showEvent so the preview renders at correct size on open and resize

## [0.9.5] - 2026-03-31 ([full changelog](https://github.com/twwat/bbdrop/compare/v0.9.4...v0.9.5))

### Added
- **Video support**: Full pipeline for video galleries — metadata extraction via pymediainfo, screenshot sheet generation with OpenCV, video-specific BBCode placeholders, strategy selection, and a dedicated Video settings tab
  - Mixed media dialog when folders contain both images and videos
  - Media type column in the queue table
  - Video files pass through to archives without re-encoding
  - Screenshot sheet preview dialog
  - Manual download links field for video galleries
- **Host context menu**: Primary/cover host selection via right-click on worker status widget

### Fixed
- **Unconfigured file hosts**: Workers no longer attempt startup when credentials are missing; shows "Credentials Required" status instead
- **Disk space warnings**: Replaced stacking QMessageBox dialogs with a single persistent warning dialog
- **Image host display names**: Host column and log messages now show display names instead of internal IDs
- **Worker status icons**: Runtime worker state now correctly reflected in icons and context menu
- **Cloudflare challenge detection**: File host login now detects and reports Cloudflare challenges instead of silently failing
- **Signal type overflow**: Large upload byte values no longer overflow pyqtSignal integer types

## [0.9.4] - 2026-03-18 ([full changelog](https://github.com/twwat/bbdrop/compare/v0.9.3...v0.9.4))

### Changed
- Removed portable tarball builds for Linux and macOS (use AppImage or .deb/.dmg instead)
- Removed Windows MSI installer (use the Inno Setup .exe or portable .zip instead)

### Fixed
- **Disk space warning freezes startup**: When disk space was already low at launch, the warning dialog appeared behind the splash screen, making the app appear frozen — now defers until the main window is visible

## [0.9.3] - 2026-03-18 ([full changelog](https://github.com/twwat/bbdrop/compare/v0.9.2...v0.9.3))

### Added
- **Archive split modes**: Choose between fixed part size or split only when exceeding the host's file size limit
  - "Only when exceeding host limit" uses each host's configured max file size as the split threshold
  - The per-host limit is user-configurable — set it to your preferred cap, not necessarily the host's actual maximum

### Changed
- Pixhost and TurboImageHost default content type changed from Family Safe to Adult
- Image host config buttons in settings remain clickable even when the host is disabled
- File host upload logs consolidated to a single message per upload with elapsed time and average speed

### Fixed
- **Image host selection not saved**: Changing the image host in quick settings was lost on restart
- **File host speed column blank**: BandwidthManager was accessed on the wrong object

## [0.9.2] - 2026-03-17 ([full changelog](https://github.com/twwat/bbdrop/compare/v0.9.1...v0.9.2))

### Added
- **Link Scanner redesign**: Dashboard replaced with a left-right split layout (host table | gallery results table)
  - Host table with health progress bars, image counts, and percentage columns
  - Gallery results table repopulates on host selection (no more tabs)
  - Bidirectional sync between host table and host dropdown
  - Overall progress bar at top, hidden when idle
- **Scan type radio buttons**: Stale / Unchecked / Problems selector replaces three separate buttons
- **Age mode dropdown**: Filter by last scan age or original upload age
- **"All" age option**: Scan all galleries regardless of age threshold
- **Info buttons**: Contextual help popovers on every scan control
- Scan coordinator credential loading for K2S-family and Rapidgator file hosts
- IMX gallery routing to RenameWorker's /user/moderate endpoint in scan coordinator

### Changed
- Link Scanner dashboard is wider (750px minimum, up from 650px)
- Host labels use canonical names (IMX.to, TurboImageHost, Rapidgator, etc.) instead of abbreviations
- Scan controls signal now carries age_mode parameter through to database query
- K2S file checker uses getFilesInfo endpoint (renamed from getFilesList)
- Coordinator callbacks routed through thread-safe pyqtSignal (fixes potential cross-thread GUI updates)
- Splash screen dimensions and corner radius adjusted

### Fixed
- Shutdown dialog in-progress step text now bolds for visibility
- **CVE-2026-32274**: Bump black to >=26.3.1 (arbitrary file writes from unsanitized cache file name)

## [0.9.1] - 2026-03-06 ([full changelog](https://github.com/twwat/bbdrop/compare/v0.9.0...v0.9.1))

### Added
- **Hash-based deduplication**: Keep2Share, TezFiles, and FileBoom skip uploads when the server already has the file, using MD5 hash matching
- **Unified host status icons**: Single icon per host shows active/enabled/disabled state and cover host at a glance
- **Pixhost support**: Upload galleries to Pixhost as a third image host option
- **Multi-cover uploads**: Detect and upload multiple cover photos per gallery with any/all matching rules
  - Per-cover success/failure tracking with visual states in the gallery table
  - Option to exclude cover images from the gallery upload
- **Cover host selector**: Choose which image host handles your cover uploads (independent of gallery host)
- **Gallery file manager**: Upgraded to tree view with better file browsing
- **Error details dialog**: Shows per-file upload failures and overall progress
- File host data (hashes, sizes, dedup status) included in gallery JSON artifacts

### Changed
- Bandwidth display uses smoothed values for steadier readings
- Cover settings simplified with rule logic radio buttons
- Settings panels now hide options that don't apply to the selected host
- Windows context menu renamed from "IMX Uploader" to "Add to BBDrop"
- Disabled hosts appear dimmed in the worker table
- Updated TurboImageHost logo

### Fixed
- **IMX galleries with broken thumbnail URLs**: API-provided BBCode was being dropped and incorrectly reconstructed
- **Windows context menu requires admin**: Now writes to per-user registry — no elevation needed
- **Settings crash on launch**: Empty values in config file caused "Not a boolean" error
- **Disk space display**: Overflow in calculations and alarm flapping between warning states
- **Crash on host logo click** in the gallery table
- **Notification sounds missing** in frozen (.exe) builds
- **Queue restore**: Galleries stuck in scanning/validating state after restart
- **Cover progress**: Cover uploads no longer interfere with gallery progress counters
- Cover uploads on TurboImageHost now fetch batch results correctly
- Assorted stability fixes for proxy tab, worker signals, and Firefox cookie caching

## [0.9.0] - 2026-02-24

### Added
- **Notifications**: Desktop toast alerts and audio notifications for upload events
  - New Notifications tab in settings with per-event audio and alert toggles
  - Plays sounds on upload completion, errors, and queue events
- **Tor support**: Route uploads through the Tor network
  - Auto-detects running Tor daemon and supports circuit renewal
  - DNS-through-proxy option prevents DNS leaks (SOCKS5_HOSTNAME)
  - Select Tor per-service, per-category, or globally from the proxy dropdown
- **Proxy support for image hosts**: IMX.to and TurboImageHost uploads now route through the proxy system (previously file hosts only)
- **Disk space monitoring**: Prevents data loss when disk fills up during uploads
  - Status bar indicator shows current disk usage with tier-based warnings
  - Configurable warning and critical thresholds in settings
  - Blocks image and file host uploads when disk space is critically low
  - Pre-flight check before archive creation
- **Auto-clear warning**: Confirmation dialog when auto-clear would remove galleries with pending Link Scanner results
- **Cover photo indicator**: Gallery table shows a visual indicator for galleries with detected covers

### Changed
- Proxy settings tab renamed to "Proxies & Tor" with a two-column grid layout
- Proxy dropdowns use clearer labels (replaces radio button mode selection)

### Fixed
- System tray icon showed a blue square instead of the app logo
- Queue data loss if app closed during upload (immediate sync save on completion/failure)
- Duplicate galleries from trailing slashes in folder paths
- Database ID collisions after deleting and re-adding galleries
- Quick settings incorrectly saving when closing the main settings dialog
- Theme and font unnecessarily reapplied when values hadn't changed
- InfoButton popups could overflow outside the app window
- Proxy resolver crash when global default was unset in older configs
- certifi bumped to 2024.7.4 (fixes CVE-2024-39689)

## [0.8.3] - 2026-02-14

### Added
- **TurboImageHost support**: Upload galleries to TurboImageHost in addition to IMX.to, with per-host settings and gallery management
- **Cover photos redesign**: New dedicated Cover Photos tab in settings
  - Auto-detect covers by filename patterns, image dimensions, or file size
  - Choose which host uploads your covers (independent of gallery host)
  - Set cover-specific thumbnail size (e.g. 600px on IMX via dedicated cover endpoint)
  - Limit max covers per gallery, skip duplicates
  - Set or clear covers manually via right-click context menu
- **Hooks**: New `%cv` (cover path) and `%cu` (cover URL) variables; hooks can also provide covers via JSON output
- **Interactive hook mapper**: Visual tool for mapping hook output fields to placeholders
- **Settings sidebar**: Vertical sidebar navigation replaces horizontal tabs
- **Stronger credential encryption**: Credentials now use a cryptographically random master key stored in your OS keyring (auto-migrated from previous versions)

### Fixed
- Settings migration from ImxUploader no longer re-runs on every launch
- Gallery storage path could contain a duplicate segment
- Host status not refreshing after toggling enabled state
- TurboImageHost reporting failed uploads as successful

## [0.8.2] - 2026-02-03

### Added
- **Pure Python split ZIP library**: Custom `splitzip` implementation for creating multi-part ZIP archives without external dependencies (no 7z CLI required)
- **Multi-format archive support**: ZIP and 7Z archive creation; ZIP, 7Z, RAR, and TAR extraction
- **Archive settings tab**: Configure archive format, compression method, and split size
- **Split archive uploads**: Large galleries split into parts with per-part tracking and template placeholders (#partLabel#, #partNumber#, #partCount#)
- **Image Hosts settings tab**: Configurable image host panel (currently imx.to, extensible for additional hosts)
- **Peak speed date tracking**: Host metrics now record the date when peak upload speed was achieved
- **Proxy test button**: Test proxy connectivity from file host config dialog with global lock
- **Host status icons**: Worker table shows enabled/disabled/auto state icons per file host
- **Tab description labels**: Descriptive headers on all settings tabs
- **Tooltips**: Added to all interactive settings widgets
- **Dimmed proxy styles**: Disabled proxy sections visually dimmed in both themes

### Changed
- Tab description font increased from 11px to 12px with background color
- Log action buttons moved below File Logging section, right-aligned
- Infinity symbol on IMX storage bar renders with symmetric loops using centered overlay label
- Worker status icons use pixmap labels instead of delegates for auto-upload status
- Theme-aware infinity label color with improved vertical centering

### Fixed
- Upload workers table column visibility, widths, and order not persisting across restarts
- Gallery count preserved when renaming tabs
- Help dialog thread crash from concurrent pygments lexer imports
- Missing User-Agent headers on file host HTTP requests

### Tests
- Comprehensive xdist parallel execution fixes (20+ test files)
- New archive manager tests (ZIP, 7Z, split archives, caching)
- New worker status icon tests (icon loading, host enable/disable, context menu)
- Test infrastructure: thread shutdown fixtures, logger state isolation

## [0.8.0] - 2026-01-27

v0.8.0: Complete proxy system, bbdrop rebrand, UI refinements

### Breaking Changes
- **Application renamed**: imxup → bbdrop
  - Main script renamed: imxup.py → bbdrop.py
  - All assets renamed: imxup*.{ico,png} → bbdrop*.{ico,png}
  - QSettings namespace: ImxUploader → BBDropUploader
  - All internal references updated (90+ files)

### Added
- **Complete proxy system**:
  - Core data models and storage with SQLite backend
  - Pool rotation and health tracking
  - 3-level proxy resolver (global → category → service)
  - pycurl proxy adapter for all file host uploads
  - Bulk import utilities for proxy lists
  - Proxy GUI widgets and dialogs
  - Full integration with file host upload system
- **New assets**: Unified check and IMX icon assets
- **Status icons**: Visual status indicators in gallery table (replacing color-coded text)

### Changed
- **Proxy UI simplification**:
  - Replaced complex `InheritableProxyControl` with `SimpleProxyDropdown`
  - Radio button mode selection (Direct/System/Manual/Pool)
  - Cleaner category and service-level proxy configuration
  - Updated file host config dialog integration
- **Branding updates**:
  - New splash screen styling with blue theme (0,124,250)
  - Updated logo positioning and sizing
  - Refreshed icon assets
  - Modified version display format
- **UI refinements**:
  - Image status dialog reorganized with QGroupBox sections
  - Gallery table uses status icons instead of colored text
  - Unified icon system with status helpers
- **Code quality**: Normalized line endings (CRLF → LF)

### Fixed
- **File hosts**: Credential persistence and storage
- **UI**: Preserve column order when adding/removing columns
- **Layout**: Splitter state restoration and sizing improvements
- **Settings**: Added TabIndex constants for proper proxy tab navigation
- Misc bug fixes and improvements

### Tests
- Added proxy system tests (core functionality)
- Added file host credential persistence tests
- Added comprehensive proxy UI tests (1,161 lines):
  - Unit tests for SimpleProxyDropdown widget (617 lines)
  - Integration tests for proxy workflows (544 lines)

## [0.7.4] - 2026-01-19

v0.7.4: Unified theme icons, bandwidth manager, table delegates

### Performance
- **Table delegates**: Reduced memory footprint by eliminating per-row widget instances
- **Icon consolidation**: Faster startup with fewer assets to load and cache

### Added
- **Centralized bandwidth manager**: Unified tracking of upload bandwidth across all workers
- **Table delegates**: Custom delegates for action buttons and file host status display
- New auto-upload mode icons (auto.png, auto-disabled.png)
- IMX light theme logo variant (imx-light.png)

### Changed
- **Asset consolidation**: Replaced 66 theme-specific icon pairs (-dark/-light) with 33 unified icons
- Updated icon manager to support theme-independent assets
- Refactored main window signal handling for bandwidth integration
- Optimized file host logos (filedot, katfile) - reduced file sizes
- Cleaned up file host client code organization
- Normalized line endings (CRLF → LF) for cross-platform consistency

### Fixed
- **Checkbox icons not loading**: Updated QSS files to reference unified `checkbox_check.png`
- Improved settings dialog icon references
- Enhanced table row rendering with delegate pattern

### Tests
- Added comprehensive tests for bandwidth manager
- Added unit tests for action button and file host status delegates

## [0.7.2] - 2026-01-10

v0.7.2: Performance optimization, modular theming, design tokens

### Performance
- **Optimize deferred widget creation**: 16-32 seconds → ~1 second (17-32x faster)
  - Viewport-first loading: visible rows (~25) created in ~50ms
  - Batch repaints with setUpdatesEnabled(False): 1144 repaints → ~11
  - Pause update_timer during batch operation
  - Reduce processEvents frequency from every 20 to every 100 rows
- Optimize selection handler to avoid O(N²) complexity

### Added
- Design tokens system for consistent theming
- Modular QSS loader with token injection
- Session length and timeframe filter to Statistics dialog
- get_hosts_for_period() for per-host statistics filtering
- Visual regression testing infrastructure
- Widget creation timing benchmark (tests/performance/)
- Comprehensive STYLING_GUIDE.md

### Changed
- Migrate inline styles to property-based QSS
- Split monolithic QSS into modular architecture
- Enhance ImageStatusDialog with ProportionalBar

### Fixed
- Improve scanner cleanup in GalleryFileManagerDialog

### Assets
- Add scan icons
- Update Keep2Share logo

### Tests
- Add visual regression testing infrastructure
- Add Statistics dialog enhancement tests
- Refactor test infrastructure and update fixtures

## [0.7.1] - 2026-01-07

v0.7.1: Statistics dialog, IMX status scanner performance, comprehensive tests

### Added
- Statistics dialog (Tools > Statistics) with session/upload/scanner metrics
  - Two-tab interface: General stats and File Hosts breakdown
  - Tracks app startups, first startup timestamp, total time open
  - Shows upload totals, fastest speed record with timestamp
  - Displays per-host file upload statistics from MetricsStore
- Add Statistics button to adaptive quick settings panel
- Add session time tracking (accumulated across app launches)
- Add format_duration() support for days (e.g., "2d 5h 30m")

### Performance
- Fix massive UI freeze in ImageStatusDialog (50+ seconds → instant)
  - Disable ResizeToContents during batch table updates
  - Block signals and suspend sorting during bulk operations
- Optimize ImageStatusChecker with batch preprocessing
  - Single batch query replaces O(n) per-path queries
  - O(1) path-to-row lookup via pre-built index
  - Batch database writes via bulk_update_gallery_imx_status()
- Add quick count feature showing "Found: X images" within 2-3 seconds

### Thread Safety
- Add threading.Lock to ImageStatusChecker for shared state protection
- Fix race condition with _cancelled flag preventing stale results
- Improve dialog cleanup timing (signals remain connected during checks)

### UI/UX
- Add animated spinner to ImageStatusDialog (4-state dot animation)
- Add theme-aware status colors (green/amber/red) for online status
- Add NumericTableItem for proper numeric sorting in tables
- Add StatusColorDelegate preserving colors on row selection
- Simplify status display to single word (Online/Partial/Offline)
- Remove detailed offline URL tree view (cleaner presentation)
- Update worker status widget with clickable icon buttons
- Optimize host logos (reduced file sizes)

### Other Fixes
- Fix is_dark_mode() using correct QSettings organization name
- Fix fastest_kbps_timestamp not being saved when record set
- Fix QSettings namespace consistency (ImxUploader/Stats)
- Fix test expectations for non-breaking space in format functions

### Tests
- Add test_statistics_dialog.py (29 tests, 99% coverage)
- Add test_image_status_checker.py (956 lines)
- Add test_image_status_dialog.py (717 lines)
- Add test_rename_worker_status_check.py (1,358 lines)
- Update test_format_utils.py with NBSP constant and days tests
- Total: ~3,400 new lines of test code

### Refactoring
- Extract format_duration() to format_utils.py (DRY principle)
- Reorganize rename_worker.py structure
- Standardize button labels in adaptive settings panel
- Apply code formatting pass to custom_widgets.py

## [0.6.15] - 2025-12-29

### Changed
- Extracted ThemeManager from main_window.py
- Extracted SettingsManager from main_window.py
- Extracted TableRowManager from main_window.py
- Extracted GalleryQueueController from main_window.py

### Performance
- Cached QSettings to reduce disk I/O
- O(1) row lookup instead of O(n) iteration
- Schema initialization runs once per database

## [0.6.13] - 2025-12-26

### Added
- Help dialog with comprehensive documentation
- Emoji PNG support for templates
- Quick settings improvements

### Changed
- Optimized theme switching speed

### Fixed
- Help dialog performance issues

## [0.6.12] - 2025-12-25

### Added
- Worker logo setting in worker status widget
- ArtifactHandler extraction for cleaner artifact management

### Changed
- Refactored worker table for better maintainability

## [0.6.11] - 2025-12-24

### Fixed
- Thread-safety issues in ImageStatusChecker
- Worker lifecycle management improvements

### Changed
- Extracted WorkerSignalHandler from main_window.py
- Wired up progress_tracker.py and removed duplicates from main_window.py

## [0.6.10] - 2025-12-23

### Added
- Feature to check online status of images on imx.to
- Image availability verification

## [0.6.09] - 2025-12-19

### Fixed
- Upload Workers queue display issues
- Event-driven updates for worker status

## [0.6.08] - 2025-12-17

### Added
- Per-host BBCode formatting support
- Advanced Settings tab in settings dialog

## [0.6.07] - 2025-12-15

### Security
- Added SSL/TLS certificate verification to FileHostClient

### Fixed
- Thread-safe cookie caching
- GUI log display settings
- Worker table scroll behavior
- RenameWorker authentication issues

### Changed
- Renamed gallery_id to db_id for clarity and consistency
- Centralized file host icon loading with security validation
- Added comprehensive docstrings to main_window.py

## [0.6.06] - 2025-12-15

### Fixed
- Worker count initialization
- Optimized INI file operations (reduced from 11 to 1 operation)
- File host worker initialization location in imxup.py
- Removed duplicate init_enabled_hosts() call

## [0.6.05] - 2025-12-11

### Added
- Worker status auto-disabled icons
- Upload timing logs
- Live queue metrics in worker status widget
- Storage display in worker status widget

### Fixed
- Metrics persistence issues
- Auto-regenerate BBcode after file host uploads complete
- File host icons for disabled hosts
- Enable/disable state change handling for file hosts

### Performance
- Skip file host icon refresh during startup (prevented 48-second freeze)

## [0.6.02] - 2025-11-26

### Fixed
- Critical 20+ minute GUI freeze from table rebuilds and deadlock
- Main thread blocking during file host upload completion
- Initialization order for worker_status_widget and FileHostWorkerManager
- GUI freeze issues
- Metrics display issues
- Files column display

### Changed
- Removed debug logging spam from icon management
- Merged feature/file-host-progress-tracking into master

## [0.6.00] - 2025-11-09

### Added
- Multi-host file upload system with 6 provider integrations
  - Fileboom (fboom.me)
  - Keep2Share (k2s.cc)
  - TezFiles (tezfiles.com)
  - Rapidgator (rapidgator.net)
  - Filedot (filedot.to)
  - Filespace (filespace.com)
- ZIP compression support for file hosts
- Token management for API-based hosts

### Fixed
- Thread safety for multi-threaded uploads

## [0.5.12] - 2025-10-27

### Added
- Adaptive Settings Panel
- External Hooks system (pre/post-upload, on-complete, on-error)
- System enhancements for hook execution

### Changed
- Complete widget extraction refactoring
- Fixed CSS typo
- Resolved signal blocking bugs

## [0.5.10] - 2025-10-23

### Added
- Multi-host uploader integration
- Template conditionals for BBCode
- Credential migration system
- External app hooks system

## [0.5.07] - 2025-10-20

### Added
- Animated upload status icons
- Gallery removal system refactoring

### Changed
- Major storage architecture refactor
- Unified path resolution through get_base_path()
- Removed hardcoded ~/.imxup references
- Support for portable/custom storage modes
- Removed obsolete migration system and legacy configuration handling

## [0.5.05] - 2025-10-19

### Added
- ZIP archive extraction support
- pycurl upload engine for improved performance
- Bandwidth tracking improvements

### Changed
- Table UI refinements

## [0.5.03] - 2025-10-16

### Added
- Theme toggle button
- Enhanced icon system

### Changed
- Improved startup performance
- Windows build improvements
- UI polish refinements

## [0.5.01] - 2025-10-15

### Added
- PyInstaller support for Windows builds

### Changed
- Major type safety improvements
- UI improvements
- Code organization refactoring

## [0.5.00] - 2025-10-09

### Added
- Comprehensive logging system overhaul
- Advanced image sampling system

### Changed
- Major UI improvements
- Refactored database operations

### Fixed
- Renamed column showing incorrect status for pending galleries
- Critical gallery_id reuse bug by clearing session cookies
- Critical row verification bug
- Critical table corruption bugs causing duplicate rows and stale mappings

## [0.4.0] - 2025-10-05

### Added
- Auto-clear feature for completed galleries

### Changed
- Refactored RenameWorker to use independent session
- Eliminated uploader dependency from RenameWorker
- Cleaned up dependencies

## [0.3.13] - 2025-10-04

### Added
- User-Agent header to all HTTP requests with platform information
- Standalone log viewer popup option in View menu
- Tab tooltip updates after drag-drop and queue operations

### Changed
- Standardized log message levels and prefixes across CLI and GUI modules
- Refactored load_user_defaults() for cleaner fallback handling
- Reduced debug noise
- Improved upload file logging with per-image timing and success messages
- Cleaned up icon manager debug output and timestamp formatting

### Fixed
- Timer shutdown warnings
- Upload concurrency improvements

## [0.3.2] - 2025-08-31

### Added
- Multi-folder selection in Browse dialog
- Configurable timeouts for uploads

### Changed
- Improved upload reliability
- Better error logging

### Fixed
- Upload failures with improved timeout handling

## [0.3.0] - 2025-08-28

### Added
- Comprehensive theming system with dark mode icons
- Dark theme icon variants for all UI states
- Centralized styles.qss for styling

### Changed
- Refactored main_window.py: extracted dialogs
- Simplified UI architecture
- Major refactoring to eliminate code duplication
- Enhanced theme loading with proper light/dark theme section parsing
- Consolidated theme-aware styling across all GUI components

### Fixed
- UI layout issues

## [0.2.0] - 2025-08-25

### Added
- Icon management system
- Enhanced upload functionality
- System tab enhancements

### Changed
- Major UI/UX improvements
- Architecture enhancements
- Refactored codebase for better modularity and maintainability
- Reduced main GUI file from 10,685 to 9,012 lines (15.6% reduction)
- Extracted modules: TableProgressWidget, GalleryQueueItem, QueueManager

## [0.1.0] - 2025-08-15

### Added
- Initial GUI implementation with PyQt6
- Splash screen
- Comprehensive Settings Dialog
- Tab management functionality
- Gallery table with context menu operations
- Cookie caching for Firefox
- Auto-archive functionality
- Background task handling
- Completion processing worker
- Non-blocking dialog handling
- Unsaved changes management

---

## Version History Summary

| Version | Date | Highlights |
|---------|------|------------|
| 0.9.2  | 2026-03-17 | Link Scanner redesign |
| 0.9.1  | 2026-03-06 | Pixhost support, multi-cover pipeline, context menu fix, 20+ bug fixes |
| 0.9.0  | 2026-02-24 | Notifications, Tor support, image host proxies, disk space monitoring |
| 0.8.3  | 2026-02-14 | Multi-host uploads, cover redesign, CSPRNG credentials, hooks |
| 0.8.2  | 2026-02-03 | Multi-format archives, split uploads, tooltips |
| 0.8.0  | 2026-01-27 | Proxy system, bbdrop rebrand, status icons |
| 0.7.4  | 2026-01-19 | Unified icons, bandwidth manager, table delegates |
| 0.7.2  | 2026-01-10 | Performance optimization, modular theming, design tokens |
| 0.7.1  | 2026-01-07 | Statistics, thread safety, performance |
| 0.6.15 | 2025-12-29 | ThemeManager, SettingsManager, TableRowManager extraction |
| 0.6.13 | 2025-12-26 | Help dialog, emoji PNG support, quick settings |
| 0.6.12 | 2025-12-25 | Worker table refactor, ArtifactHandler, worker logos |
| 0.6.11 | 2025-12-24 | Thread-safety fixes, worker lifecycle improvements |
| 0.6.10 | 2025-12-23 | Image online status checking |
| 0.6.09 | 2025-12-19 | Worker queue display fixes |
| 0.6.08 | 2025-12-17 | Per-host BBCode, Advanced Settings |
| 0.6.07 | 2025-12-15 | SSL/TLS verification, security improvements |
| 0.6.06 | 2025-12-15 | INI optimization, initialization fixes |
| 0.6.05 | 2025-12-11 | Worker status improvements, startup optimization |
| 0.6.02 | 2025-11-26 | Critical GUI freeze fixes |
| 0.6.00 | 2025-11-09 | Multi-host file upload (6 providers) |
| 0.5.12 | 2025-10-27 | Adaptive Settings, External Hooks |
| 0.5.10 | 2025-10-23 | Template conditionals, credential migration |
| 0.5.07 | 2025-10-20 | Animated icons, storage refactor |
| 0.5.05 | 2025-10-19 | ZIP extraction, pycurl engine |
| 0.5.03 | 2025-10-16 | Theme toggle, startup performance |
| 0.5.01 | 2025-10-15 | PyInstaller, type safety |
| 0.5.00 | 2025-10-09 | Logging overhaul, image sampling |
| 0.4.0 | 2025-10-05 | Auto-clear, RenameWorker refactor |
| 0.3.13 | 2025-10-04 | Logging improvements, User-Agent |
| 0.3.2 | 2025-08-31 | Multi-folder selection, timeouts |
| 0.3.0 | 2025-08-28 | Dark mode theming, dialog extraction |
| 0.2.0 | 2025-08-25 | Modular architecture, UI/UX |
| 0.1.0 | 2025-08-15 | Initial release |
