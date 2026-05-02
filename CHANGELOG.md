# Changelog

All notable changes to Crush will be documented in this file.

## [Unreleased]

### Bug Fixes

- **Realm table viewer: OverflowError when navigating integer columns** — `_read_scalar_leaf` accepted scheme=1 arrays with element widths up to 64 bytes (512-bit integers). Passing such values to Qt's `QVariant` raised `OverflowError: int too big to convert` in the terminal whenever the table was sorted or scrolled. Realm integer columns never use widths above 8 bytes; scheme=1 arrays wider than that are now rejected and the column is skipped rather than returning garbage data.
- **Realm column mapping via spec colkeys** — the previous "last N sub-arrays" heuristic for mapping cluster entries to user columns silently broke whenever a BackLink column was present between user columns, assigning the BackLink slot to the wrong user column. The parser now reads the explicit 64-bit column keys from `spec→child[5]` and derives the physical cluster index via `(colkey & 0xFFFF) + 1`, producing a correct cluster-index → user-column-index map. BackLink entries (type 14) are filtered out of both the map and the column-type list. The heuristic is kept as a fallback for older format variants that lack `spec→child[5]`.
- **Realm timestamp columns decoded incorrectly** — columns with type code 8 (Timestamp) were fed through the nullable-integer decoder, which misread the nanoseconds sub-array as a null-bitmap and produced wrong values (Unix-epoch-1970 dates). A dedicated `_read_timestamp_column` decoder is now called first for any type-8 column; it follows the 1-indexed seconds array structure (position 0 holds the INT_MAX null sentinel, positions 1..N hold row data) and formats values as `YYYY-MM-DD HH:MM:SS UTC`.
- **Realm row count wrong for sparse tables** — `_derive_row_count` used a most-common-element-count heuristic across cluster sub-arrays. Tables where most columns were empty (count = 0) or where all non-empty columns were reference arrays (skipped by the heuristic) returned row_count = 0, causing the timestamp decoder to fail with a count mismatch. The parser now reads the ObjKey array at cluster[0] — which always has exactly one entry per row — as the authoritative row count, falling back to the heuristic only if cluster[0] is unreadable.
- **Realm nullable boolean columns showed raw integers** — 2-bit scheme=0 arrays (Realm's nullable boolean encoding: 0 = False, 1 = True, ≥ 2 = NULL) were returned as raw integers 0/1/2/3. `_read_scalar_leaf` now converts 2-bit values to `False`, `True`, or `None` immediately after decoding.
- **Realm NULL-only columns missing from output** — columns whose entire payload is absent (scheme=1, width=0, e.g. `outside_link`, `livetext_edition_id`) were silently dropped. They now appear in the table with an all-`None` list so the column is visible in the viewer.

### Improvements

- **Realm file type label** — `.realm` files now show `Realm` as the fast type label in the VFS tree panel, consistent with how SQLite, bplist, ABX, and SEGB files are labelled. Previously, `.realm` files showed no label at all.
- **Realm column names (format 24)** — the parser now reads column names from the correct spec node (`spec → child[1]` rather than `child[0]`, which holds type codes). Previously every column was labelled `col_0`, `col_1`, … regardless of the actual schema names.
- **Realm string column decoding (format 24 cluster architecture)** — format 24 stores strings in fixed-width inline entries (scheme=1) where `content_length = (entry_width − 1) − last_byte`. This replaces the incorrect legacy pointer-following logic that produced garbage string values. The generalised decoder handles any byte-width entry: 8-byte entries (≤ 7 chars) and 16-byte entries (≤ 15 chars) are both decoded; entries whose last byte equals or exceeds the width are decoded as NULL; non-zero "oversized" last bytes indicate a heap pointer and are shown as `<long>`.
- **Realm link column display** — link columns (ObjKey references stored in narrow ref arrays, width < 32) are now decoded as their raw integer values instead of being misinterpreted as string pointer arrays. Wide ref arrays (width ≥ 32) still go through the legacy indirect-string decoder as a fallback.
- **Realm column-to-name mapping** — in the format 24 cluster layout the user-visible columns occupy the *last N* sub-arrays (the leading sub-arrays are internal, e.g. ObjKey and metadata). The parser now maps sub-array indices to 0-based user-column indices correctly, so the table viewer shows named columns in the right order.
- **Realm column type labels** — the parser reads column type codes from `spec→child[0]` and maps them to human-readable names (int, bool, string, date, link, …). Type names are shown next to column names in the Schema tab and stored per table for use by the timestamp decoder.
- **Realm Schema tab: columns and types** — the Schema tab now shows each table as an expandable node listing all column names with their Realm type (e.g. `dt_created → date`, `is_prime → bool`). Tables without decoded data still appear as leaf entries labelled "(no column data decoded)".
- **Realm Tables tab: SQL queries** — decoded table data is loaded into a temporary in-memory SQLite file when the Tables tab opens. The SQL bar is now fully functional: `SELECT`, `WHERE`, `ORDER BY`, aggregates, and cross-table `JOIN`s all work. The temp file is deleted automatically when the tab is closed.
- **Realm Tables tab: cross-table JOIN support via `_objkey`** — each table in the temporary SQLite database receives a leading `_objkey` column containing the Realm ObjKey for every row. Realm link columns store ObjKey values of the referenced table, so joins can be written as `JOIN class_ArticleEDP e ON a.edp = e._objkey`. ObjKeys are not shown in the table grid; they are only present in the SQL database.

### Testing

- **Realm forensic test coverage** — five new `@pytest.mark.forensic` tests covering the same categories already used for SQLite:
  - *Source Immutability* — `RealmParser` must leave the source file bytes unchanged after parsing.
  - *No Side Effects* — `RealmParser` must not create any sibling files next to the evidence file.
  - *Read-only Media* — `RealmParser` must succeed when the evidence directory is `chmod 0o555` and the file is `0o444`.
  - *Known-output Verification* — `minimal.realm` must always parse to exactly `schema = ["metadata", "class_Evidence"]`, `Tables found = 2`.
  - *Reproducibility* — parsing the same Realm file twice must produce structurally identical results.
- **`minimal.realm` reference fixture** — a 112-byte synthetic Realm file is committed to `crush/tests/fixtures/` with its SHA-256 checksum in `checksums.json`. The corpus integrity guard now covers Realm alongside the existing SQLite, plist, ZIP, and TAR fixtures.

## [0.6.0] — 2026-05-01

### New Features

- **Export as .logarchive** — iOS diagnostics nodes (`diagnostics/`) now have an "Export as .logarchive…" right-click action. Crush assembles the logarchive (diagnostics tree + uuidtext sibling) in a temporary directory and copies the result to a user-chosen location, producing a standard `.logarchive` folder that can be opened in other tools.
- **SQLite timestamp column decoding** — right-clicking a column header in the SQLite / table viewer now offers a "Decode column as timestamp" submenu. Supported formats: Unix seconds, Unix milliseconds, Unix microseconds, Mac Absolute Time (seconds since 2001-01-01), Windows FILETIME (100 ns since 1601-01-01), and Chrome / WebKit time (µs since 1601-01-01). The decoded values are displayed as `YYYY-MM-DD HH:MM:SS UTC`; the column header shows the active format as a suffix (e.g. `created_at [unix ms]`). Sorting remains chronologically correct because the raw numeric value is preserved internally. Select "Clear timestamp format" to revert.
- **Parallel Apple Unified Log conversion** — Multi-Log Studio now splits large logarchives and iOS diagnostics across multiple `unifiedlog_iterator` processes (one per physical core by default). Entries stream into the viewer as each chunk finishes rather than waiting for the full conversion. On a typical 200 MB acquisition this yields a ~25 % wall-time reduction; the speedup scales with the number of tracev3 files and available cores.
- **Paste & Decode** — **Tools → Paste & Decode…** opens a dialog where you can paste raw hex, base64, or plain text and open it immediately in any supported viewer. The input encoding is auto-detected (or can be forced), and the target format is chosen from a dropdown (Auto-detect, Binary plist, XML plist, JSON, XML, SQLite, Realm, Android Binary XML, SEGB / Biome, Protobuf, or raw Hex view). Useful for inspecting data copied out of a hex editor, BLOB cell, or network capture without saving it to disk first.

### Bug Fixes

- **Paste & Decode: Protobuf option silently fell back to auto-detect** — the Protobuf parser was not registered in the parser registry, so selecting "Protobuf (schema-less)" in the Paste & Decode dialog had no effect and auto-detection was used instead. The parser is now registered (explicit-only: it never wins in auto-detection but is reachable by name).
- **Multi-Log Studio hang on close during unified log conversion** — closing the Multi-Log Studio window while Apple Unified Log data was still being converted caused the whole application to freeze until the conversion finished (potentially many minutes). The underlying `unifiedlog_iterator` subprocess is now killed immediately when the window is closed, and the worker thread exits within milliseconds.
- **Apple Unified Log timestamps missing in Multi-Log Studio** — when loading an iOS full-filesystem acquisition directly, all log entries showed "—" in the Timestamp column. The root cause was that `unifiedlog_iterator` does not follow symbolic links for `timesync/` directories; the parallel mini-archive setup now copies `timesync/` and `Special/` into each chunk instead of symlinking them. Additionally, the CSV timestamp format emitted by the binary (`2024-01-15 10:23:45.123456789 +0000`, with a space before the timezone offset) was not handled by the timestamp parser; this is now fixed.

### Improvements

- **SQLite WAL forensic analysis:**
  - *WAL Frames (generated)* — new combo entry appears whenever a `-wal` companion is present. Shows a full frame inventory (Frame / Page / Transaction / Status / Table / Offset) with every frame classified as **Active**, **Superseded**, **Uncommitted**, or **WAL slack** (salt-mismatch frames from a previous WAL cycle, per Sanderson's terminology). Superseded and uncommitted frames are colour-coded amber and blue respectively so the examiner immediately sees whether overwritten or in-flight data exists. The Table column shows which schema object owns each page, resolved by walking the B-tree from `sqlite_master` root pages.
  - *Show WAL history toggle* — a **Show WAL history** checkbox appears in the table toolbar whenever the active table has non-Active frames in the WAL. When enabled, the table gains a **WAL Source** column and rows decoded from Superseded, Uncommitted, and WAL-slack frames are appended below the current data with colour coding (amber / blue / gray). The row count label shows how many additional rows were recovered from WAL history.
  - *DB Info WAL summary* — when a WAL is present, six WAL metrics (file size, total frames, active / superseded / uncommitted / WAL-slack counts) are prepended to the DB Info view above the PRAGMA list, with amber/blue highlights on non-zero forensic counts.
  - *Raw page access* — double-clicking any WAL frame row extracts the raw page bytes (frame offset + 24 to skip the frame header) and opens them in the hex viewer, labelled `WAL frame N — page M`.
  - *WAL discovery for single-file open* — when a `.db` file is opened directly (not from inside a ZIP or folder), the parser now also checks the real filesystem for a `-wal` / `-shm` companion next to the file. Previously `FileVFS` scoped to the single file only, so companions were silently skipped.
  - *Parser read-only connection* — the SQLite parser now opens its internal connection with `mode=ro` (URI flag), preventing the automatic WAL checkpoint that previously destroyed the WAL companion before the viewer could read it.
- **SQLite / Table viewer — schema and settings inspection:**
  - *Summary view* now shows tables and views with row counts; the status label reports the full schema object count (tables, views, indexes, triggers) at a glance.
  - *DB Structure (generated)* — new combo entry listing all schema objects (tables, views, indexes, triggers) with structural details: column list for tables, CREATE SQL for views, `ON table (columns)` for indexes, and the first line of CREATE TRIGGER for triggers.
  - *DB Info (generated)* — new combo entry showing 28 PRAGMA settings in a three-column layout (Setting / Value / Description), styled after the DB Browser for SQLite "Edit Pragma" view. Enum values are decoded to their named constant (e.g. `2 — FULL` for auto_vacuum), booleans show as `1 — ON` / `0 — OFF`. The integrity_check hint pre-fills the SQL bar for on-demand use.
  - *Views in the selector* — database views are added to the combo box (below a separator) and are fully browsable like tables.
  - *SQL bar enhancements* — `PRAGMA` statements are now accepted alongside `SELECT`/`WITH`. Status feedback appears below the input field in red on error and default color on success. Selected text only: if a query fragment is highlighted, F5 / Run executes only that selection, enabling step-by-step debugging of complex queries.
  - *SQL syntax highlighting* — keywords, strings/identifiers, numbers, and comments are highlighted; colors adapt to light and dark palette.
  - *Resizable panes* — a splitter between the SQL bar and the results table lets the examiner maximise the data area.
- **Theme moved to View menu** — the Theme submenu (System default / Light / Dark) has been moved from **Tools** to **View**, where display-related settings belong.
- **Refinement of File Format Database entries** - all entries were double checked, the descriptions refined and relevant URLs added.

### Testing

- **Forensic integrity test suite** — added `crush/tests/test_forensic.py` with 14 tests that verify the tool is safe to run on real evidence. Tests are grouped into five categories and each carries a human-readable description of the forensic property it checks:
  - *Source Immutability* — DirectoryVFS, ZipVFS, and TarVFS must leave every source file or archive byte-identical after a full read.
  - *No Side Effects* — SQLiteParser must not create WAL, journal, or any other sibling file next to the evidence.
  - *Read-only Media* — all three VFS types and SQLiteParser must work correctly when the evidence file and its directory are `chmod 0o444 / 0o555`, simulating write-protected forensic media.
  - *Known-output Verification* — four committed reference artifacts (SQLite, binary plist, ZIP, TAR) must always parse to their exact pre-computed values.
  - *Reproducibility* — parsing the same artifact twice must produce structurally identical results.
- **WAL preservation test** — `test_sqlite_parser_preserves_wal_companion` verifies that parsing a WAL-mode database leaves the `-wal` companion byte-identical in the temporary working copy. The test simulates a live acquisition: a writer commits data to the WAL while a reader holds an open transaction (preventing auto-checkpoint), and the parser is run in that window. This test would have caught the read-write connection bug that silently checkpointed the WAL before the viewer could read it.
- **Reference corpus with checksum guard** — `crush/tests/fixtures/` contains four committed binary test-evidence files (`minimal.sqlite`, `minimal_binary.plist`, `minimal.zip`, `minimal.tar.gz`) with a `checksums.json` of their SHA-256 digests. `conftest.py` verifies every checksum before the first test runs and aborts the session with a clear `TAMPERED` message if any file has changed.
- **Forensic audit report** — every test run automatically generates `reports/forensic_audit.html`: a self-contained, printable HTML document structured by forensic category with intro text per section and a Reference Corpus table showing file names, SHA-256 hashes, and sizes. In CI the report is uploaded as the `forensic-test-report` artifact (90-day retention).

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
