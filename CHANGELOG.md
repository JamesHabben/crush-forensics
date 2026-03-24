# Changelog

All notable changes to Crush will be documented in this file.

## [0.2.0] — 2026-03-24

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
