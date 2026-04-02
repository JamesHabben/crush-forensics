# Changelog

All notable changes to Crush will be documented in this file.

## [Unreleased - Only in Nightly Build]

### New Features

- **Log Viewer** — any file can be opened as a structured log viewer via right-click → *Open as Log Viewer*. The parser auto-detects the log format (JSON Lines, Android logcat, Syslog RFC 3164, generic timestamp-prefixed, plain text fallback) and normalises entries into timestamp, severity level, process/tag, and message fields. Multiline log events (e.g. embedded dictionaries or stack traces) are grouped into a single entry; the table shows the first line with a continuation count badge (`[N more lines]`), and the full raw event is shown in the detail panel below.
- **Log Viewer: level filter** — toggle buttons for ERROR / WARN / INFO / DEBUG / TRACE / UNKNOWN instantly filter the visible entries.
- **Log Viewer: time range filter** — when timestamps are present, an optional from/to date-time picker restricts entries to a chosen time window. Entries without a parsed timestamp always remain visible.
- **Log Viewer: timezone selector** — timestamps are displayed in UTC by default; a *Display TZ* selector switches the table and time-range picker to the local system timezone. The internal comparison always uses UTC.
- **Log Viewer: text search** — free-text filter across the message and process/tag fields.
- **Log Viewer: detail panel** — selecting a row shows the complete raw log event (including continuation lines) in a resizable panel below the table; the panel height can be dragged freely with the splitter.

### Improvements

- **Filesystem panel: flat search results view** — typing in the filter field now replaces the tree with a flat list of all matching files and folders, including their full path. Double-clicking a file opens it directly; double-clicking a folder clears the filter and navigates the tree to that folder (expanding all parents automatically). Clears the filter to return to the normal tree.
- **Filesystem panel: typed search syntax** — filter supports `name:x` and `type:x` tokens (e.g. `type:sqlite`, `name:rubin type:sqlite`). Plain text without a token prefix is treated as a name filter. Multiple tokens are AND-combined.
- **Filesystem panel: background type indexing** — on load, Crush pre-scans all files in the background to populate the format detection cache. Progress is shown in the status bar (`Indexing types`); once complete, `type:` searches are instant. A spinner in the status bar indicates any ongoing background activity.
- **Status bar spinner** — an animated spinner appears alongside background activity messages so it is immediately clear that work is in progress.
- **Nightly builds** — automated nightly builds for Linux and Windows are published as a pre-release on GitHub via a new GitHub Actions workflow. The previous nightly is replaced on each run.
- **Nightly build version display** — nightly builds now show a build identifier in the window title, status bar, and About dialog (e.g. `Crush 0.2.1 (20260329-nightly)`), making it immediately clear which build is running. Release builds continue to show only the semantic version.
- **Filesystem panel: Type column labels** — the Type column now shows the detected file type; folders display `DIR` and unknown types display `-`.
- **Filesystem panel: search results context menu** — added **Open Containing Folder** to jump from a search hit back to its folder in the tree.
- **Filesystem panel: search size sorting** — the Size column in search results now sorts numerically by raw bytes (ignoring the displayed `KB/MB/GB` suffixes).
- **Format identification: no extension fallback** — format detection now relies solely on magic bytes and parser matches; filename extensions are no longer used for identification.
- **Format knowledge base: unknown magic offsets** — magic-byte entries may now use `offset: None` for trailer/unknown offsets (informational only), e.g. DMG `koly` trailer.
- **Format Reference: QA and Links** - Ony reviewed formats are published in the GUI. All referenced Links are clickable, Magic Bytes are given in hex with offset.
### Documentation

- User handbook updated with full filter/search syntax reference, type indexing explanation, and corrected descriptions for Open folder… and PDF support.

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
