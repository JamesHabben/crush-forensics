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
- Open via context menu: **Open as** → **Protobuf**.
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
- Protobuf payloads decoded automatically: double fields in the plausible Cocoa-timestamp range get a `[possible Cocoa timestamp: ...]` hint alongside the raw number (same range check as the schema-less Protobuf Viewer — see Protobuf Viewer Limitations), nested messages expanded inline with a `[raw: N B: hex…]` hint alongside them (wire type 2 doesn't declare that the bytes really are a submessage — see Protobuf Viewer Limitations), repeated fields collected into arrays. Length-delimited fields that don't decode as UTF-8 or as a nested message are shown as a `<N B: hex…>` preview rather than being dropped. Full protobuf field number range (up to 2²⁹−1) is supported.
- A backing SQLite database is created on open, enabling SQL queries via the built-in editor with autocomplete. The `Payload` column holds human-readable rendered text; `Payload JSON` holds the same data as JSON for `json_extract` queries — floats are always stored as JSON numbers (never swapped for a date string) so comparisons stay type-consistent:
  - Single field: `json_extract("Payload JSON", '$.2')` → value of field 2
  - Nested field: `json_extract("Payload JSON", '$.6.1')` → sub-field 1 of field 6
  - Repeated field: `json_extract("Payload JSON", '$.9[0]')` → first occurrence of field 9
- Double-clicking a Payload cell always opens the raw protobuf bytes in the Blob Inspector.

Limitations
- Record parsing is best-effort; some records may show a warning.
- Payloads that cannot be decoded as protobuf are stored as raw bytes accessible via the Blob Inspector.

### LevelDB
- Parses LevelDB directories and displays records in the Table Viewer.

Limitations
- Works on directories only, not single files.
- Displays the first 2,000 records for performance.

### Realm Database
- Parses `.realm` files and opens them in the Realm Viewer.
- Extracts: file header metadata, schema/class list, top-ref comparison across header slots, and table/column data.
- Column decoding is spec-driven — each column's on-disk layout (Cluster/ClusterTree B+-tree, and each of Int/Bool/String/Binary/Timestamp/Float/Double/Decimal128/ObjectId/UUID/Link/LinkList/Set/Dictionary) is dispatched from its actual declared type, not guessed from the data's shape.
- SQL queries run against a temporary SQLite representation of the data; the SQL editor supports autocomplete. Tables with Link/LinkList columns get a matching `v_<table>` view with those columns already resolved to the linked row's data.
- Double-clicking a Summary row navigates directly to that table.
- The Views tab resolves Link/LinkList columns to chosen columns of the linked table interactively, opened as a new tab (no SQL needed).
- BLOB column cells expose raw bytes in the Blob Inspector on double-click.
- Encrypted `.realm` files (Realm's built-in AES-256-CBC + HMAC-SHA224 per-page encryption) are supported when the 64-byte encryption key is known — right-click the file → **Open as** → **Realm DB (Encrypted)…**, enter the key as a hex string. This is a raw key the app itself generates and stores (e.g. Keychain/Keystore), not a password — there is no key-derivation step. Auto-detection on a normal double-click open is intentionally not attempted (a header that fails to decode is equally consistent with "encrypted" and "corrupt/non-standard", and content alone can't distinguish the two), so encrypted files are only recognized as `.realm` at all via their extension.

Limitations
- An encrypted file without a `.realm` extension cannot be identified as a Realm database at all — its content is ciphertext, indistinguishable from random bytes without the key, so there is no reliable content-based signal to fall back on the way there is for unencrypted files (the "T-DB" mnemonic).
- Dictionary<K,Mixed> columns are decoded — a per-row 2-slot array whose slots are independent BPlusTree roots for keys and values, paired by index position (dictionary.cpp), with the key's declared type read from the spec's `m_types` array rather than the colkey. Values are always Mixed, same decoder/limitations as Mixed columns below.
- Mixed and TypedLink values are decoded on their own or as a List/Set/Dictionary-value element. A Mixed value that itself holds a nested List/Set/Dictionary is expanded too (recursively, up to a depth cap that guards against a corrupt/malicious reference chain), with a nested Dictionary always treated as String-keyed since there is no Spec column to read a key type from in that case. Geospatial values (`type_Geospatial`) have no dedicated on-disk case in Realm Core's Mixed storage at all, so any occurrence falls through to a clearly labelled "unsupported type" marker rather than being silently dropped or shown as blank.
- Decimal128, ObjectId, UUID, Mixed, Float/Double, and Dictionary are all dispatched from the declared type same as every other column — none of them are guessed from shape. They are verified against hand-built synthetic test data matching the on-disk format spec (and, for Mixed's Decimal128 word order and UUID's byte order specifically, against the relevant Realm Core source directly) rather than a confirmed real-world sample of that type, since none has appeared in the files this parser has been tested against so far.
- On a corrupt or partially-overwritten file, if a Cluster leaf's own row-count slot can't be read, the row count is recovered by cross-checking the (still spec-defined) element counts of that leaf's column arrays instead — a corruption-recovery vote across redundant copies, not a guess on well-formed data. Affected tables are marked "(estimated — file corruption)" in the Schema tab and get a note in the Summary tab; this never happens on an intact file.
- Parse failures fall back to Hex Viewer.

### Images
- Routes supported image formats to the Image Viewer.
- Extracts a focused set of EXIF metadata (camera, time, GPS, dimensions).

Limitations
- EXIF coverage is not complete; only a subset of tags is shown.
- Decoding depends on Qt image codecs installed on the system.
- IFD entries are capped at 512 per directory, and SHORT/LONG/RATIONAL tag arrays at 8 items; data beyond the cap is not read. HEIF/HEIC/AVIF: the TIFF block's start offset inside the container's `exif` payload is located by pattern/offset heuristics (pillow-heif doesn't expose it directly) — on an HEIF variant whose prefix doesn't match, EXIF silently comes back empty rather than partially wrong.

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
- **Apple Unified Log** (`.tracev3` / `.logarchive`): parsed via the bundled Mandiant `unifiedlog_iterator` binary. Extracts timestamp, level, process, PID, subsystem, category, event type (`logEvent`, `activityCreateEvent`, `signpostEvent`, `lossEvent`, etc.), euid, and message entries. `lossEvent` entries (buffer overflow gaps) are flagged as WARN. Private/Sensitive `message_entries` are annotated `[private]` / `[sensitive]` — data that is redacted in live logs but may be present in offline acquisitions.
- Multiple files can be loaded simultaneously into a shared, merged timeline.
- Custom formats can be defined via a named-group regex and a `strptime` timestamp format; profiles are saved to `~/.config/crush/log_profiles/`.

Limitations
- Not auto-detected by default; must be opened explicitly.
- Timestamp parsing is heuristic for unrecognised formats; logcat logs do not include the year.
- Year is assumed to be the current year for Syslog (RFC 3164).
- Apple Unified Log parsing requires the platform `unifiedlog_iterator` binary (included in portable builds; run `scripts/download_unifiedlog_binaries.py` when running from source).
- Apple Unified Log: when a `.tracev3` is parsed without a matching boot record, `unifiedlog_iterator` outputs Unix-epoch-relative timestamps (landing near 1970) instead of real wall-clock time. Any entry timestamp before 2000-01-01 is therefore left blank in the Timestamp column rather than shown as a misleading date — but the excluded value is never discarded, only moved: it's kept in the entry's `extra["excluded_timestamp"]` field, visible in the detail panel, since a genuinely tampered/reset device clock would also produce a pre-2000 timestamp and that's evidence, not noise.

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
- Level toggles (ERROR / WARN / INFO / DEBUG / TRACE / UNKNOWN), free-text search (message, process, PID, subsystem, category), time-range filter with calendar pickers, and per-source visibility toggle.
- Sources are colour-coded; each appears as a chip in the source bar that toggles the source on/off.
- Background async loading: the tab opens immediately and rows stream in as they are parsed; files of any size are supported without blocking the UI.
- Column sorting runs in a background thread — the UI stays responsive during sort; a progress bar appears while sorting large datasets.
- Virtual model: no Qt item objects per cell — handles 200 k+ entries with low memory overhead.
- Custom format profiles: define a named-group regex (groups `timestamp`, `level`, `process`, `pid`, `message`; extras go to a side panel), a `strptime` string, an optional line-start regex for multiline events, and a level translation map. Live preview highlights each group in a distinct colour. Profiles are saved as JSON and reloaded on next start.
- Detail panel shows the raw original line(s) and any extra fields (e.g. `subsystem`, `category`, `event_type`, `euid`, `thread_id` for Apple Unified Log entries).
- Context menu: copy message, copy raw line, copy selection as TSV, filter by column value (pins an exact-match filter chip below the toolbar).
- **Column filter bar** — a persistent text-input row above the log table with one field per filterable column (Level, Process, PID, Subsystem, Category, Message); typing performs a live contains-match filter complementing the right-click exact-value filter.

Limitations
- Time filtering only applies to entries with a parsed timestamp.
- Multiline event grouping for custom formats requires an explicit line-start regex.

### Realm Viewer
- Tabbed view: **Header** (file metadata), **Schema** (class/table list, with Link/LinkList target tables shown), **Top Refs** (comparison across header slots), **Tables** (column data), **Views** (interactive Link/LinkList resolution), **Freed Data**, **Strings**, **Hex Preview**.

Limitations
- On a corrupt or partially overwritten file, a column's name may be unrecoverable and falls back to `col_0`, `col_1`, etc.

### Protobuf Viewer
- Schema-less decode in a tree view (field numbers, wire types, values).
- Wire type 2 (length-delimited) doesn't declare whether a payload is a nested message, a string, or opaque bytes — a field is rendered as a nested message when its bytes happen to parse as one, but a dimmed "raw bytes" hint is always shown alongside it, the same way numeric fields show every plausible interpretation, since a short blob can coincidentally be grammatically valid protobuf without actually being a submessage.
- Optional schema-based decode after loading a `.proto` file or descriptor set.

Limitations
- Schema-based decoding depends on the protobuf Python library and valid schemas.

## Known Gaps (Planned)

- Extended EXIF/metadata viewer
- PDF page rendering (not just text extraction)
- Type/extension filters in the filesystem panel
