# Changelog

All notable changes to Crush will be documented in this file.

## [Unreleased - Only in Nightly Build]

### New Features

- **Multi-Log Studio** — dedicated viewer for large and multi-source log analysis, replacing the old single-file Log Viewer:
  - **Virtual model** — `QAbstractTableModel` backed directly by a Python list; no Qt item objects per cell, ~10× less memory than the previous `QStandardItemModel`-based viewer; handles 200k+ entries without affecting startup time.
  - **Async background loading** — log files are parsed in a worker thread and streamed to the UI in chunks of 5 000 entries; the tab opens immediately and rows appear as they arrive; a 4 px indeterminate progress bar indicates loading state.
  - **Multi-source merged timeline** — multiple log files open simultaneously in a shared, timestamp-sorted table; each source gets a colour-coded chip in the source bar; chips toggle individual sources on/off without reloading.
  - **"Add to Multi-Log Studio"** — right-clicking any file in the VFS tree adds it to the currently active studio tab (or opens a new one); the "Add Source" button inside the viewer opens a file dialog for the same purpose.
  - **Unified filters** — level toggles (ERROR / WARN / INFO / DEBUG / TRACE / UNKNOWN), free-text search across message, process, PID and all extra fields, and an optional time-range filter with calendar pickers; all filters apply across all loaded sources simultaneously.
  - **Custom format profiles** — "Format…" button opens a dialog to define arbitrary log formats via a named-group regex (`timestamp`, `level`, `process`, `pid`, `message`; any other group → extra fields), a `strptime` timestamp format, an optional line-start regex for multiline events, and a level translation map; live preview highlights each named group in a distinct colour on the raw input lines (300 ms debounce); profiles are saved as JSON in `~/.config/crush/log_profiles/` and reloaded automatically.
  - **Re-parse with custom format** — *Apply* in the format dialog re-parses the selected source in-place using the custom parser without affecting other sources.
  - **Detail panel** — selected row shows the raw original line(s) and, below a separator, any extra fields (e.g. `subsystem`, `category`, `thread_id` from Apple Unified Log).
  - **Context menu** — copy message, copy raw line, or copy the full selection as TSV.
  - **Columns** — Source (colour-coded), Timestamp, Level, Process / Tag, PID, Message.

### Improvements

- **Log Viewer retired** — the old synchronous single-file Log Viewer (`QStandardItemModel`, blocking parse on open) has been removed; "Open in Multi-Log Studio" is the new entry point for all log analysis.

### Fixes

- **Source bar expanding window** — adding a second log source to Multi-Log Studio no longer causes the application window to grow wider than the screen; the source chip bar now uses a non-resizable `QScrollArea` with a horizontal scrollbar instead of propagating the chip container's preferred width to the window geometry.

- **Realm Database Viewer** — multi-tab viewer for `.realm` files:
  - **Header tab** — decodes the 24-byte file header: both top references, mnemonic, file format version, active root flag.
  - **Schema tab** — extracts the full class/table list (e.g. `class_Driver`, `class_Event`, `class_Photo`) by following the B+ tree from the active root into the schema group array; class names reveal which app features were active and what data categories are present.
  - **Top Refs tab** — decodes both root reference arrays (`top_ref[0]` / `top_ref[1]`) side by side using the correct Realm array header structure (checksum, flag bit-groups, element count, payload size); a diff summary highlights changed fields — the inactive branch may contain superseded data not yet checkpointed.
  - **Tables tab** — walks the full B+ tree to extract column data for every table; decoded column types: string (3-entry canonical leaf, 2-entry legacy leaf without null bitmap, per-row scheme=2 array, per-row direct pointer), binary/blob (N+1 offsets leaf, displayed as hex preview), scalar (bit-packed integers and booleans via `width_scheme=0`, byte-aligned integers via `width_scheme=1`). Row count is derived from the data columns themselves rather than from the unreliable child[7] backlink array.
  - **Hex Preview tab** — raw hex dump of the file.
- **Realm array header decoding** — complete implementation of the 8-byte Realm array header spec: all five flag bit-groups (`is_inner_bptree_node`, `has_refs`, `context_flag`, `width_scheme`, `width_ndx`), the three `width_scheme` payload-size formulas, the `width_ndx`→width translation table, and 8-byte payload alignment.
- **Full-file Realm parsing** — the parser now reads the entire file (not just the first 256 KB) so that column data stored near the end of large databases is not silently missed.

### Improvements

- **Hex viewer context menu** — right-clicking a selection now offers *Copy Selected Hex* (space-separated hex bytes) and *Copy Selected ASCII* (printable characters only) in addition to the existing toolbar buttons and the standard *Copy All* entry.
- **Realm format identification** — magic-byte detection via the `T-DB` mnemonic at offset 16 and `.realm` extension fallback.
- **Magic-byte sniffing** — increased VFS peek size to cover offset-based signatures beyond the first 16 bytes.

### Documentation

- **Format Knowledge Base** — Realm forensic relevance updated: documents schema extraction capability, WAL-like journaling pair, and forensic significance of class names.
- **TODO.md** — full Realm array header specification derived from the Cobley/Geneste handbook chapter, cross-checked against `f1de.realm`.

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
