# Changelog

All notable changes to Crush will be documented in this file.

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
