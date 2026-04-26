# Changelog

All notable changes to Crush will be documented in this file.

## [Unreleased - Only in Nightly Build]

### New Features

- **Export as .logarchive** — iOS diagnostics nodes (`diagnostics/`) now have an "Export as .logarchive…" right-click action. Crush assembles the logarchive (diagnostics tree + uuidtext sibling) in a temporary directory and copies the result to a user-chosen location, producing a standard `.logarchive` folder that can be opened in other tools.
- **SQLite timestamp column decoding** — right-clicking a column header in the SQLite / table viewer now offers a "Decode column as timestamp" submenu. Supported formats: Unix seconds, Unix milliseconds, Unix microseconds, Mac Absolute Time (seconds since 2001-01-01), Windows FILETIME (100 ns since 1601-01-01), and Chrome / WebKit time (µs since 1601-01-01). The decoded values are displayed as `YYYY-MM-DD HH:MM:SS UTC`; the column header shows the active format as a suffix (e.g. `created_at [unix ms]`). Sorting remains chronologically correct because the raw numeric value is preserved internally. Select "Clear timestamp format" to revert.
- **Parallel Apple Unified Log conversion** — Multi-Log Studio now splits large logarchives and iOS diagnostics across multiple `unifiedlog_iterator` processes (one per physical core by default). Entries stream into the viewer as each chunk finishes rather than waiting for the full conversion. On a typical 200 MB acquisition this yields a ~25 % wall-time reduction; the speedup scales with the number of tracev3 files and available cores.
- **Paste & Decode** — **Tools → Paste & Decode…** opens a dialog where you can paste raw hex, base64, or plain text and open it immediately in any supported viewer. The input encoding is auto-detected (or can be forced), and the target format is chosen from a dropdown (Auto-detect, Binary plist, XML plist, JSON, XML, SQLite, Realm, Android Binary XML, SEGB / Biome, Protobuf, or raw Hex view). Useful for inspecting data copied out of a hex editor, BLOB cell, or network capture without saving it to disk first.

### Bug Fixes

- **Multi-Log Studio hang on close during unified log conversion** — closing the Multi-Log Studio window while Apple Unified Log data was still being converted caused the whole application to freeze until the conversion finished (potentially many minutes). The underlying `unifiedlog_iterator` subprocess is now killed immediately when the window is closed, and the worker thread exits within milliseconds.
- **Apple Unified Log timestamps missing in Multi-Log Studio** — when loading an iOS full-filesystem acquisition directly, all log entries showed "—" in the Timestamp column. The root cause was that `unifiedlog_iterator` does not follow symbolic links for `timesync/` directories; the parallel mini-archive setup now copies `timesync/` and `Special/` into each chunk instead of symlinking them. Additionally, the CSV timestamp format emitted by the binary (`2024-01-15 10:23:45.123456789 +0000`, with a space before the timezone offset) was not handled by the timestamp parser; this is now fixed.

## [0.5.0] — 2026-04-25

### New Features

- **macOS support** — portable builds are now available for Apple Silicon (arm64). Nightly and release builds include a `crush-macos.tar.gz` artifact alongside the existing Linux and Windows builds. Running from source on macOS has always worked; this adds an official build and support badge.

### Performance

- **ZIP pre-scan** — file-type indexing now reads ZIP entries in physical storage order instead of alphabetical order, eliminating random seeks and significantly reducing scan time on large archives

### Improvements

- **Multi-Log Studio column filters** — added a persistent text-input row above the log table with one field per filterable column (Level, Process, PID, Subsystem, Category, Message); typing performs a live contains-match filter, complementing the existing right-click exact-value filter
- **Forensic Mode renamed to Integrity Mode** — the feature previously called "Forensic Mode" is now called "Integrity Mode" throughout the UI (status badge, Tools menu, tooltips, and log messages). Behaviour is unchanged; the new name better reflects that the feature is about integrity verification (hashing) rather than implying a specific legal or procedural context.
- **Nightly build identifier** — the build stamp shown in **Help → About** now includes the short commit SHA (e.g. `20260425-nightly-a3f9c12`) so nightly builds are precisely traceable.
- **About dialog** — added a direct link to the issue tracker; corrected CCL third-party attribution.
- **Bug reporting** — issue tracker link added to the README, user handbook, and About dialog.

### Documentation

- Added `CONTRIBUTING.md` with development setup, checks, and build process.
- Added `SECURITY.md` with vulnerability reporting instructions.
- JSON Viewer, XML Viewer, and LevelDB Viewer added to the README feature list (these viewers were already present but not documented).

## [0.4.1] — 2026-04-21

### Performance

- **File type indexing** — Multi-thread support for directories. Minimized the necessary unpacking of files for ZIP/Tar.
- **Apple Unified Log** — removed the hard 600-second subprocess timeout; large logarchives (1 GB+) no longer abort mid-conversion

## [0.4.0] — 2026-04-19

### New Features

- **Multi-Log Studio** — dedicated viewer for large and multi-source log analysis, replacing the old Log Viewer:
  - Load multiple log files simultaneously into a shared, merged timeline; each source is colour-coded and can be toggled on/off independently
  - Level toggles, free-text search (message, process, PID, subsystem, category), and time-range filter with calendar pickers
  - **Apple Unified Log support** — `.tra## [0.3.0] — 2026-04-03cev3` files and `.logarchive` bundles are parsed directly; extracts subsystem, category, event type, euid, and message entries; `lossEvent` gaps and Private/Sensitive entries are clearly annotated
  - **Column filters** — right-click any cell to pin an exact-match filter for that column; active filters shown as removable chips below the toolbar
  - **Custom format profiles** — define arbitrary log formats via a named-group regex with live preview; profiles saved and reloaded automatically
  - Background loading and sorting — the UI stays responsive at all times; a progress bar shows sort activity on large datasets
  - **Folder log discovery** — right-click a folder to open all recognised log files at once via a checklist dialog
- **Realm Database Viewer** — multi-tab viewer for `.realm` files: header decode, schema/class extraction, top-ref comparison, and table/column data decoding

### Improvements

- **Log Viewer retired** — replaced by Multi-Log Studio; "Open in Multi-Log Studio" is the new entry point for all log analysis
- **Hex viewer** — right-click a selection to copy as hex bytes or ASCII
- **BLOB Inspector** — same copy-as-hex / copy-as-ASCII actions available inside the inline hex view

### Fixes

- **Multi-Log Studio source bar** — adding a second source no longer causes the window to grow wider than the screen
- **SEGB v1 detection** — SEGB v1 files without a recognised extension are now auto-detected correctly
- **Realm format identification** — `.realm` files are now reliably identified by magic bytes
- **Magic-byte sniffing** — increased peek size to cover offset-based signatures beyond the first 16 bytes

## [0.3.0] — 2026-04-03

### New Features

- **Log Viewer** — open any file as structured logs with auto-detection (JSON Lines, logcat, syslog, timestamped, plain text), level/time/text filtering, timezone control, and a detail panel for full events (including multiline).
- **Protobuf Viewer** — explicit “Open as Protobuf Viewer” with schema-less wire decoding and optional schema-based decoding via `.proto` or descriptor sets.

### Improvements

- **Filesystem panel search overhaul** — flat results view, typed filters, context menu shortcuts, size sorting, type labels, and background type indexing with status spinner.
- **Forensic mode enhancements** — status badge toggle (with context menu), source hashing on ZIP/TAR/file open, and export hash manifests.
- **Tree viewer: expand/collapse all** — added toolbar buttons to expand or collapse the entire hierarchy at once.
- **Nightly builds** — automated prereleases plus build identifier display across the UI.
- **Format identification & reference** — magic-byte detection improvements and a curated, link-rich format reference.

### Fixes

- **Export: crash when re-exporting after a prior export** — export now safely handles a finished/cleared worker thread.

### Documentation

- User handbook updated with filter/search syntax, type indexing explanation, and forensic mode notes.

## [0.2.1] — 2026-03-25

### Fixes

- **Windows theme inversion** — menus and context menus were unreadable on Windows because the native Windows style partially ignores the application QPalette; the Fusion style is now applied on Windows so all palette colours are honoured correctly
- **SQLite viewer: numeric column sorting treated as string sort** — columns with integer or real values (including TEXT columns storing numeric strings) now sort numerically when clicking the column header
- **SQLite viewer: summary "Rows" column sorted as string** — row counts in the summary view now sort numerically
- **Properties panel: name and path not selectable** — file name and path labels now have text selection enabled; all property values can be marked and copied via right-click

## [0.2.0] — 2026-03-24 (updated)

### Fixes (post-release)

- **Portable build: `formats.db` not found** — corrected `--add-data` destination path in PyInstaller build and added `sys._MEIPASS` path resolution for frozen executables
- **Portable build: `libmagic` missing on Windows** — Windows build now installs `python-magic-bin` which bundles the required `magic1.dll`
- **About dialog unreadable in dark mode** — acknowledgements table now uses palette colours instead of hardcoded light-mode values
- **`MediaViewer` import failure on systems without PulseAudio** — guarded with `try/except ImportError`; app starts cleanly without audio support

### New Features

- **TAR archive support** — open `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tar.xz` acquisitions directly
- **PDF viewer** — extracts and displays text content; falls back to hex if pypdf is not installed
- **EXIF metadata** — camera make/model, GPS coordinates, timestamp, ISO, aperture extracted from JPEG/TIFF/PNG images and shown in the Properties panel
- **Artifact chaining** — SQLite BLOB cells can be opened as a new viewer tab (right-click → Open as new tab), enabling inspection of embedded plists, images, and other binary data
- **Format Knowledge Base** — bundled `formats.db` identifies 33 forensic file formats by magic bytes and extension; format name, platforms, and forensic relevance shown in the Properties panel for every opened file, including unsupported formats
- **Format Info popup** — right-click any file → Show Format Info for an instant format summary without opening a viewer tab
- **Help → Format Reference** — searchable table of all known formats with reference links
- **Hex viewer pagination** — navigate files larger than 256 KB with Prev/Next page buttons; search now jumps to the correct page automatically
- **Text viewer encoding detection** — automatically detects UTF-8, UTF-16 LE/BE (with and without BOM); detected encoding shown in toolbar
- **SQLite WAL/SHM support** — companion `-wal` and `-shm` files are automatically included when opening a database, providing the most current view of the data
- **SQLite row limit notice** — tables truncated at the display limit show a clear notice; full data accessible via SQL query

### Improvements

- Properties panel always shows all four MACB timestamp fields; unavailable fields (e.g. from ZIP/TAR sources) display `—` with an explanatory note
- Per-table and per-record error handling in SQLite, plist, SEGB, and LevelDB parsers — partial results shown instead of crashes on malformed data
- LevelDB parser now correctly cleans up temporary files after parsing
- Hex fallback parser identifies unknown formats by magic bytes and surfaces forensic context

### Documentation

- `crush/docs/handbook.md` — user handbook covering all features and forensic workflow tips
- `crush/admin/format_knowledge_base.md` — admin guide for maintaining the format knowledge base
