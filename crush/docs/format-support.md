# Format Support — Parsers & Viewers

This page lists what Crush can parse and how each viewer behaves, plus the current limitations. It is meant to be honest and actionable: if something is missing, you will see it here.

## How Detection Works

- File types are identified by magic bytes, not by extension.
- A parser is chosen from the registry in priority order. If no parser matches, the Hex Viewer is used.
- Some parsers are explicit-only and must be selected via the context menu.

## Parsers (What They Do)

### SQLite Database
- Detects SQLite by magic bytes and loads tables and rows into the Table Viewer.
- Copies companion `-wal` and `-shm` files if present.

Limitations
- Table display is capped at 10,000 rows per table. Use SQL queries to load more.
- WAL is only used to show the current committed state when `-wal`/`-shm` are present; WAL is not parsed for deleted or historical records.
- SQLite itself is not carved for deleted records.
- Parse failures fall back to Hex Viewer.

### Property List (plist)
- Parses binary and XML plists into the Tree Viewer.
- Attempts to decode NSKeyedArchiver plists when possible.

Limitations
- NSKeyedArchiver decoding is best-effort and may fall back to raw structures.
- Parse failures fall back to Hex Viewer.

### XML
- Parses XML into the Tree Viewer.
- Flattens Android-style `<map>` structures for easier reading.

Limitations
- Not a validating parser; malformed XML shows an error record.
- Plist XML is handled by the plist parser instead.

### JSON
- Parses JSON into the Tree Viewer.

Limitations
- Assumes UTF-8 input; non-UTF encodings may show replacement characters.
- Parse errors show an error node in the Tree Viewer.

### Protobuf (Explicit Only)
- Open via context menu: **Open as Protobuf Viewer**.
- Performs a schema-less wire-format decode and displays it in the Protobuf Viewer.

Limitations
- Schema-less decode shows field numbers and wire types only.
- Schema-based decoding requires a `.proto` file or descriptor set.

### Android Binary XML (ABX)
- Decodes ABX v1/v2 into a structured tree and reconstructed XML (ABX Viewer).

Limitations
- Best-effort decode; newer ABX variants may not parse.

### SEGB (Biome)
- Parses SEGB v1/v2 records into the Table Viewer.

Limitations
- Record parsing is best-effort; some records may show a warning.
- Record payloads are shown as hex previews only (no semantic decoding yet).

### LevelDB
- Parses LevelDB directories and displays records in the Table Viewer.

Limitations
- Works on directories only, not single files.
- Displays the first 2,000 records for performance.

### Images
- Routes supported image formats to the Image Viewer.
- Extracts a focused set of EXIF metadata (camera, time, GPS, dimensions).

Limitations
- EXIF coverage is not complete; only a subset of tags is shown.
- Decoding depends on Qt image codecs installed on the system.

### Media (Audio/Video)
- Routes supported media formats to the Media Viewer (playback).

Limitations
- Detection is extension-based.
- Playback depends on system multimedia codecs.

### PDF
- Extracts text using `pypdf` and shows it in the Text Viewer.

Limitations
- Without `pypdf` installed, PDFs open in Hex Viewer with a note.
- Some PDFs have no extractable text (scanned or protected files).

### Log Files (Explicit Only)
- Open via context menu: **Open in Multi-Log Studio**.
- Auto-detects JSON Lines, Android logcat, Syslog (RFC 3164), and generic timestamped/plain-text logs.
- Multiple files can be loaded simultaneously into a shared, merged timeline.
- Custom formats can be defined via a named-group regex and a `strptime` timestamp format; profiles are saved to `~/.config/crush/log_profiles/`.

Limitations
- Not auto-detected by default; must be opened explicitly.
- Timestamp parsing is heuristic for unrecognised formats; logcat logs do not include the year.
- Year is assumed to be the current year for Syslog (RFC 3164).

### Hex Fallback
- Any file without a matching parser opens in the Hex Viewer.
- If the format database recognizes it, the Properties panel shows name and forensic context.

Limitations
- Raw bytes only; no structured decoding.

## Viewers (What They Do)

### Table Viewer
- Sortable grid, row filtering, SQL queries (SELECT only), CSV export.
- BLOB inspection and "Open as new tab" for embedded artifacts.
- For SQLite databases, the Summary view lists tables and computes row counts.

Limitations
- Read-only; write queries are blocked.
- Large datasets are capped by parser limits (e.g., SQLite 10,000 rows).

### Tree Viewer
- Hierarchical view for plist/XML/JSON structures with search and copy.

Limitations
- Read-only; no inline editing or advanced type casting.

### Text Viewer
- Line numbers, search, and lightweight syntax highlighting.
- Auto-detects common encodings (UTF-8 and common UTF-16 variants).

Limitations
- Non-UTF encodings may show replacement characters.
- Highlighting is heuristic, not a full parser.

### Hex Viewer
- Paged hex + ASCII view, hex and ASCII search, copy options.

Limitations
- Read-only; no edit mode.
- Copy is page-based, not entire file bytes.

### Image Viewer
- Fit-to-window scaling, zoom, magnifier.

Limitations
- No rotate/crop/export controls in the viewer.

### Media Viewer
- Playback with scrub and time display.

Limitations
- Dependent on OS/Qt codec support.

### ABX Viewer
- Split view with parsed tree and reconstructed XML.

Limitations
- XML reconstruction is best-effort.

### Multi-Log Studio
- Level toggles (ERROR / WARN / INFO / DEBUG / TRACE / UNKNOWN), free-text search (message, process, PID, and all extra fields), time-range filter with calendar pickers, and per-source visibility toggle.
- Sources are colour-coded; each appears as a chip in the source bar that toggles the source on/off.
- Background async loading: the tab opens immediately and rows stream in as they are parsed; files of any size are supported without blocking the UI.
- Virtual model: no Qt item objects per cell — handles 200 k+ entries with low memory overhead.
- Custom format profiles: define a named-group regex (groups `timestamp`, `level`, `process`, `pid`, `message`; extras go to a side panel), a `strptime` string, an optional line-start regex for multiline events, and a level translation map. Live preview highlights each group in a distinct colour. Profiles are saved as JSON and reloaded on next start.
- Detail panel shows the raw original line(s) and any extra fields (e.g. `subsystem`, `category`, `thread_id` for Apple Unified Log entries).
- Context menu: copy message, copy raw line, copy selection as TSV.

Limitations
- Time filtering only applies to entries with a parsed timestamp.
- Multiline event grouping for custom formats requires an explicit line-start regex.
- Apple Unified Log (`.logarchive` / `tracev3`) binary format is not yet parsed; plain-text exports from `log show` are supported.

### Protobuf Viewer
- Schema-less decode in a tree view (field numbers, wire types, values).
- Optional schema-based decode after loading a `.proto` file or descriptor set.

Limitations
- Schema-based decoding depends on the protobuf Python library and valid schemas.

## Known Gaps (Planned)

- Unified Logs
- Extended EXIF/metadata viewer
- PDF page rendering (not just text extraction)
- Type/extension filters in the filesystem panel
