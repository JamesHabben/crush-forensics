# Changelog

All notable changes to Crush will be documented in this file.

## [Unreleased]

### New Features

- **HEIC / HEIF / AVIF / JPEG XL image support** — the image viewer now renders HEIC, HEIF, AVIF, and JPEG XL files in addition to the existing formats. Qt's native decoder is tried first (fastest path, zero overhead for already-supported formats); if it cannot handle the format, Pillow decodes the image and transfers raw pixels directly to Qt — no intermediate PNG encode, minimising decode latency. EXIF metadata (GPS coordinates, device make/model, timestamp, ISO, aperture) is extracted from HEIC/HEIF containers and displayed in the Properties panel, consistent with existing JPEG/TIFF/PNG EXIF support. **Known limitation:** HEIC/HEIF is a multi-image container (burst frames, HDR layers, depth maps, Live Photo previews); only the primary image is currently shown.
- **Plist / tree viewer — BLOB inspector** — right-clicking any field in the plist tree viewer now shows "Inspect BLOB…"; for raw `bytes` values the bytes are passed through directly, for dicts and lists the subtree is serialized to XML plist first, and for scalars the value is wrapped in a plist envelope — consistent with the BLOB inspector behavior in the SQLite, Realm, SEGB, and LevelDB viewers.

### Improvements

- **Magic-byte type detection — HEIC / HEIF / AVIF / JXL** — the filesystem panel now returns format-specific type labels (`HEIC`, `HEIF`, `AVIF`, `JXL`) detected from the ISOBMFF `ftyp` brand and JXL container/codestream signatures, before falling through to the `filetype` library. Files with a misleading extension (e.g. a `.mp4` or `.jpeg` that is actually a HEIC container) are correctly identified and labelled by content.
- **`type:image` search — full image category** — the filesystem panel `type:image` filter is now category-aware and matches all image formats — JPEG, PNG, HEIC, HEIF, AVIF, JXL, WebP, TIFF, GIF, BMP — even when their specific type label (e.g. `HEIC`) does not literally contain the word `image`. Use `type:heic`, `type:avif`, or `type:jxl` to narrow to a specific format.

- **NSKeyedArchiver — extended type converter** — added conversions for `NSData`/`NSMutableData` (→ `bytes`), `NSNull` (→ `None`), and `NSDateComponents` (→ readable string); implemented as a wrapper around the vendored ccl_bplist converter so the third-party file remains unmodified.
- **NSKeyedArchiver — unknown custom classes** — when a deserialized dict still carries `$class`/`$classname` metadata (unknown class not handled by the converter), the tree viewer now shows the class name in the Type column and hides the internal `$class`/`$classes`/`$classname` keys, so only the actual data fields are visible.
- **PlistParser — additional supported extensions** — `.sfl` and `.archive` added to `SUPPORTED_EXTENSIONS`; these files were already parsed correctly via magic-byte detection, the list now reflects reality.
- **PlistParser — NSKeyedArchiver deserialization failure surfaced** — a failed `deserialise_NsKeyedArchiver` call was silently swallowed; the Format field in the Properties panel now reads `binary (NSKeyedArchiver — deserialization failed)` and a warning is logged, while the raw plist structure is still shown in the tree.
- **BLOB inspector — NSKeyedArchiver deserialization** — the "Plist / bplist" format option in the BLOB inspector now goes through the full `deserialise_NsKeyedArchiver` path (same as the file parser), so SQLite BLOBs and nested plist data values that contain NSKeyedArchiver payloads show the decoded object graph instead of the raw `$objects`/`$top` internal structure.
- **Plist / tree viewer — string and list BLOB serialization** — when opening the BLOB inspector on a plain string field, the value is now passed as raw UTF-8 (no XML plist envelope, no surrounding quotes); list/tuple subtrees that cannot be plist-serialized fall back to newline-joined items rather than Python's `repr()` notation with brackets and inner quotes.

### Bug Fixes

- **Floating dock panels — cannot resize on Wayland** — floating `QDockWidget` windows used the `Qt::Tool` window type, which on KDE/GNOME Wayland compositors is drawn without resize handles; switching to `Qt::Window` when floating gives the panel full compositor decorations including borders.
- **Floating dock panels — move/resize broken after first interaction** — the custom title bar called `startSystemMove()` for dragging, which fails on Wayland after a resize because the compositor no longer tracks an active button press; replaced with manual delta-based dragging on non-Wayland, and the Wayland/XWayland check now also covers `XDG_SESSION_TYPE` and `WAYLAND_DISPLAY` environment variables to correctly catch XWayland sessions.
- **XML plist — files with DOCTYPE opened in hex viewer** — the parser registry peeked only 64 bytes, too few to reach the `<plist>` root tag past Apple's standard DOCTYPE declaration (~150 bytes); peek size raised to 256 bytes so `PlistParser` correctly claims `.plist` files with an XML preamble.
- **XML plist — plist root-tag detection simplified** — the previous logic navigated past `<?…?>` and `<!…>` blocks by searching for their closing `>`, which failed silently when those blocks extended past the peek window; replaced with a direct `<plist` substring search, which is simpler and equally unambiguous.
- **Format label — XML files (SVG, XHTML, …) misidentified as "XML plist"** — `FormatDatabase.identify()` matched any file starting with `<?xml` against the XML plist entry without verifying the root tag; it now calls `_looks_like_plist_xml()` as an additional guard before returning that match.

## [0.9.0] — 2026-05-16

### New Features

- **SEGB / Biome viewer** — complete forensic overhaul of the SEGB v1/v2 parser:
  - Protobuf payloads decoded automatically: Cocoa timestamps shown as ISO datetimes, nested messages expanded inline, full field-number range supported (up to 2²⁹−1), repeated fields collected into arrays.
  - Backing SQLite database created on open with autocomplete-enabled SQL editor. `Payload` column shows human-readable text; `Payload JSON` column enables `json_extract("Payload JSON", '$.N')` field queries (nested: `$.N.M`, repeated: `$.N[i]`).
  - Raw protobuf bytes always accessible via Blob Inspector on double-click.
- **New themes** — *Geek* (phosphor-green terminal), *Purple* (synthwave), and *Ocean* (cyan/navy) added under *View → Theme*; all persist across sessions.
- **Rainbow theme + custom snapshot** — *View → Theme → Rainbow* cycles the UI palette through the full colour spectrum; a *⏸ Snapshot* button in the status bar lets you pause, name, and save the current hue as a permanent custom theme entry.

### Improvements

- **Table viewers — cell detail panel** — a collapsible pane below the table shows the full content of the currently selected cell and updates live on click or keyboard navigation. Decoded text (e.g. SEGB protobuf payload) is shown where available; binary BLOBs fall back to a UTF-8 decode or a hex preview with a byte-count hint. Applies to SQLite, SEGB, and Realm viewers.
- **Table viewers — wide-column usability** — columns are now capped at 400 px after auto-sizing so a single long cell can no longer force the table far off-screen; holding **Shift** while scrolling moves the table horizontally. Applies to SQLite, SEGB, and Realm viewers.
- **BLOB Inspector — "Decoded (from table)" view** — when opening the BLOB Inspector on a cell that has a decoded display (e.g. SEGB protobuf payload), a *Decoded (from table)* option is inserted at the top of the format dropdown and selected by default, showing the human-readable content immediately. Raw bytes are always preserved, so switching to *Protobuf (schema-less)*, *Hex*, or any other format mode continues to work correctly on the original binary data.
- **SQLite viewer — SQL autocomplete** — context-aware completion for table/view names after `FROM`/`JOIN` and column names after dot notation; aliases resolved automatically.
- **SQLite viewer — summary navigation** — double-clicking a table row in the Summary tab jumps directly to that table.
- **Realm / SQLite viewers** — BLOB cells now expose raw bytes to the Blob Inspector on double-click; SQL autocomplete and summary-tab navigation work in the Realm viewer.

### Bug Fixes

**SEGB / Biome**

- **SEGB viewer — spurious Bundle ID / Stream ID / Payload Timestamp columns removed** — these columns appeared empty for most entries because the field number mapping was based on incorrect assumptions about the SEGB protobuf schema; removed to avoid misleading analysts. The full protobuf payload remains accessible via the `Payload` and `Payload JSON` columns.
- **SEGB — Inspect Cell / double-click inconsistency on decoded columns** — double-clicking a payload cell sent raw bytes to the BLOB Inspector while right-click *Inspect Cell…* sent the decoded text string; choosing *Protobuf (schema-less)* in the inspector then produced garbage because it tried to parse the text as wire format. Both paths now always send raw bytes and pass the decoded text separately as the *Decoded (from table)* default view.
- **Show Format Info — SEGB files reported as Unknown** — right-clicking a SEGB file and choosing *Show Format Info* always reported "Unknown format": (a) the format lookup only peeked 32 bytes, too few to reach the SEGB v1 magic at offset 52; (b) SEGB v2 (magic at offset 0) had no entry in `formats.db`. Both are fixed; a `detect_fast_label` fallback is also applied so format detection is consistent with the filesystem panel.

**SQL Editor**

- **SQL editor — run selected query** — running a selection was rejected with *"Only SELECT queries allowed"* due to a Unicode paragraph-separator stripping bug; fixed. Affects SQLite, SEGB, and Realm viewers.
- **SQL editor — fixed height** — the SQL input could not grow when the panel below was resized; now expands freely with a 6-line minimum.

**Realm**

- **Realm viewer — summary double-click navigation** — double-clicking a table row in the Summary tab did not navigate to that table; fixed (the "Row" prefix column shifted the name to column 1 while the handler always read column 0).

**Platform / UI**

- **macOS rendering** — tab close buttons, tab colours, and file-tree expand arrows all rendered incorrectly with the native Qt style; switching to Fusion style (already used on Windows) fixes all three.
- **Linux / Wayland — floating dock panels could not be resized** — undocking a panel on Wayland triggered a *"mouse grab only for popup windows"* warning and the panel had no resize handles; caused by the custom dock title bar added in a previous release, which prevents the Wayland compositor from providing its own decorations. On Wayland the custom title bar is now skipped so the window manager handles move and resize natively.
- **Filter history — Enter key** — pressing Enter committed the top history suggestion instead of the typed text; fixed by switching completion mode.

**AppImage**

- **AppImage — missing execute permission** — the nightly CI pipeline uploaded the AppImage as an artifact and re-downloaded it without restoring the execute bit, causing file managers to open it as a disk image instead of running it; fixed by adding `chmod +x` in the release job.
- **AppImage — Open External broken** — `xdg-open` failed silently because AppImage environment variables leaked into the subprocess; stripped before invocation.

### Build / Distribution

- **Native packages** — Linux AppImage, macOS ZIP (Apple Silicon + Intel), Windows ZIP produced by CI.
- **Bundle size** — unused Qt modules stripped; macOS artifacts use `ditto` to preserve framework symlinks.
- **Application icon** — window icon set at runtime on all platforms; Wayland app-id registered via `setDesktopFileName`.

---

## [0.8.0] — 2026-05-10

### New Features

- **Recent files menu** — *File → Open Recent* lists the last 10 opened files, archives, and folders (full path shown, persisted across sessions); includes a *Clear Recent* option.
- **Filter history*b* — the filesystem panel filter field remembers the last 30 used filters (persisted across sessions); click the field to browse history, or type to narrow by substring. Filter applies on Enter; picking from the dropdown applies immediately.
- **LevelDB viewer** — LevelDB databases are parsed in a dedicated viewer:
  - *Overview* — all `MANIFEST-*` files (active one labelled *(current)*), comparator, sequence number, and files by level.
  - *Files* — per-file summary with size, key ranges, and live/deleted/unknown counts; deleted files highlighted red.
  - *Records* — all records with live/deleted state, sortable *Offset* (byte position in source file), split *Key* / *Value* hex pane, state filter, free-text search, and *Export CSV…*.
  - *Forensic columns* — full *Internal Key* (user key + 8-byte sequence/type suffix) for `.ldb`/`.sst` files; CSV exports include complete hex-encoded key and value bytes.
  - *Cell inspector* — right-click any row for *Inspect Key…*, *Inspect Value…*, or *Inspect Internal Key…* in the BLOB Inspector.
  - *LOG tabs* — `LOG` and `LOG.old` shown in dedicated read-only tabs with a *Find* toolbar.
- **Realm Freed Data — cell inspector** — right-clicking a freed block now offers *Inspect Block…* in the BLOB Inspector.
- **BLOB Inspector — new decode modes** — *Protobuf (schema-less)*, *Android Binary XML (ABX)*, *Image (PNG / JPEG / GIF)*, and *JSON* modes added; all auto-detected in Auto mode where applicable.

### Improvements

- **atime preservation** — `DirectoryVFS` and `FileVFS` no longer update the access time of source evidence files (Linux: `O_NOATIME`; Windows: atime restored after read; macOS: not yet implemented).
- **BLOB Inspector — non-blocking** — opens as a non-modal window; multiple inspectors can be open simultaneously.
- **Paste & Decode — inline result** — decoded output appears in the same window instead of a separate tab.
- **macOS badge** — README updated to reflect source-only macOS support (no working pre-built executable).

### Testing

- **Forensic timestamp/atime preservation** — new tests verify that `DirectoryVFS`, `ZipVFS`, `TarVFS`, `SQLiteParser`, `RealmParser`, and `LeveldbParser` do not modify mtime, ctime, or atime of source evidence files.

---

## [0.7.0] — 2026-05-04

### Bug Fixes

- **SQLite WAL support from ZIP** — fixed incorrect path resolution preventing WAL from loading correctly.
- **Realm table viewer crash (OverflowError)** — fixed Qt overflow when decoding invalid >64B integer widths; unsupported scheme=1 widths are now rejected.
- **Realm schema mapping (BackLink issue)** — replaced heuristic column mapping with explicit `spec→child[5]` colkey mapping; BackLink (type 14) excluded.
- **Realm timestamp decoding** — fixed type-8 decoding where nanoseconds were misinterpreted as a null bitmap.
- **Realm row count mismatch** — row count now derived from ObjKey array instead of heuristic, fixing sparse table issues.
- **Realm nullable booleans** — correct decoding of 2-bit values (True / False / None instead of raw integers).
- **Realm NULL-only columns missing** — now preserved and displayed as all-`None` columns.

---

### Improvements

- **Realm Freed Data tab** — added view of free-space entries with offset, size, source refs, decoded content, and hex view. Entries are color-coded by source ref state.
- **Realm Top Refs diff** — added child-level comparison of root structure (count, width, flags); offset diff removed as non-informative.
- **Dual Top Ref decoding** — active and previous snapshots are now both parsed and available for comparison.
- **Top Refs schema diff** — added detection of added/removed tables and row-count changes between snapshots.
- **Realm file labeling** — `.realm` files now correctly identified in the VFS tree.
- **Schema tab overhaul** — real column names and types are now displayed instead of generic `col_N`.
- **Format 24 decoding fixes**
  - correct string decoding (fixed-width inline entries)
  - correct column ordering (last-N user columns)
  - correct link column handling (ObjKey refs)
- **Type system improvements** — column types now parsed from schema and shown consistently across Schema and Tables tabs.
- **SQL support in Tables tab** — in-memory SQLite database enables full querying, including JOINs.
- **Cross-table joins** — link columns can be joined directly via ObjKey-based mapping.

---

### Testing

- **Realm forensic test suite**
  - immutability check (no modification of source file)
  - no side effects (no sibling files created)
  - read-only media support
  - deterministic output validation
  - known fixture validation (`minimal.realm`)
- **Corpus integrity expansion** — Realm added to existing SQLite/plist/ZIP/TAR test coverage with SHA-256 verified fixture.

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
