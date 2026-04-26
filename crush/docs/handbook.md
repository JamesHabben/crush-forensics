# Crush — User Handbook

## What is Crush?

Crush is a Digital Forensic Analysis Workbench for examining iOS and Android acquisitions. It lets you open archives (ZIP, TAR), folders, and individual files, then navigate and inspect their contents using format-aware viewers — without extracting anything to disk first.

Crush includes a built-in **file format database** covering forensically relevant formats across iOS and Android. For every file you select or open, Crush identifies the format by magic bytes (not by extension), then shows its name, platform, forensic relevance, and a link to the format specification — even for formats that have no dedicated viewer yet. The database is a work in progress — more formats and references will be added over time.

---

## Opening Evidence

Use the **File** menu to load a source:

| Menu item | When to use |
|---|---|
| **Open file…** | Single file — image, database, plist, etc. Opens directly in a viewer tab |
| **Open ZIP archive…** | iOS full-filesystem acquisitions, IPA files, any `.zip` |
| **Open TAR archive…** | Android ADB acquisitions, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tar.xz` |
| **Open folder…** | Already-extracted acquisition or any folder of files on disk |

Opening a file (**Open file…**) appends it to the existing tree as a new root node, so multiple files can be open side by side. Opening a ZIP, TAR, or folder replaces the current tree.

---

## The Interface

```
┌─────────────────┬──────────────────────────────────┬───────────────┐
│  Filesystem     │         Viewer tabs               │  Properties   │
│  panel (left)   │                                   │  panel (right)│
│                 │                                   │               │
│                 │                                   │               │
└─────────────────┴──────────────────────────────────┴───────────────┘
│  Log panel (bottom, hidden by default)                              │
└─────────────────────────────────────────────────────────────────────┘
```

All panels are dockable and can be floated, resized, or hidden via **View** menu. Use **View → Reset Panel Layout** to restore defaults.

---

## Filesystem Panel

The left panel shows the loaded archive or folder as a tree.

- **Double-click** a file to open it in a viewer tab
- **Single-click** selects a file and updates the Properties panel
- **Right-click** a file or folder for options:
  - **Open** — best viewer for the format
  - **Open in Hex** — force raw hex view
  - **Open as Plain Text** — force text view
  - **Open in Multi-Log Studio** — structured log viewer with level/time/text filtering and multi-source support
  - **Add to Multi-Log Studio** — adds the file as an additional source to the currently open studio tab
  - **Open as Protobuf Viewer** — schema-less Protobuf decode (optionally load a `.proto` schema)
  - **Open External (Default)** — hand off to the OS default application
  - **Open External (Choose App…)** — pick an application
  - **Show Format Info** — opens a popup showing the identified format name, category, platforms, parser support status, and forensic relevance. For known formats an **Open Reference…** button links to the format specification. Also updates the Properties panel. Works for unsupported formats — useful for quickly understanding what a file is before deciding how to examine it
  - **Export…** — extract the file or folder to disk

**Filtering:** type in the filter box at the top of the panel to search across the entire loaded tree. All searches are case-insensitive and match anywhere in the value.

While the filter is active, the tree is replaced by a **flat search results list** showing every match with its full path — no need to navigate through parent folders. Clear the filter (or click the **×** button) to return to the normal tree.

**Search syntax**

| Input | Behaviour |
|---|---|
| `rubin` | Plain text — matches all files and folders whose name contains `rubin` |
| `name:rubin` | Explicit name filter — identical to plain text |
| `type:sqlite` | Matches all files whose detected format contains `sqlite` (e.g. `SQLite Database`) |
| `name:rubin type:sqlite` | AND — only files whose name contains `rubin` **and** whose type contains `sqlite` |

Multiple tokens are always AND-combined. The `type:` token matches against the format label shown in the Type column (e.g. `jpeg`, `plist`, `xml`, `sqlite`).

**Interacting with results**

- **Double-click a file** — opens it directly in a viewer tab
- **Double-click a folder** — clears the filter and navigates the tree to that folder, expanding and selecting it automatically
- **Single-click** — selects the item and updates the Properties panel
- **Right-click** — same context menu as the tree (Open, Hex, Export, etc.)

**Type indexing**

When an archive or folder is opened, Crush starts a background type scan that reads the first bytes of every file to detect its format. While this is running, a spinner and `Indexing types` message appear in the status bar. Once complete, `type:` searches are instant. The scan typically takes a few seconds to a minute depending on archive size — for a 45 GB archive with 162,000 files, expect around 10 seconds.

---

## Viewer Tabs

Each opened file gets its own tab. Tabs can be:
- Closed with the **×** button or middle-click
- Kept open while you navigate elsewhere — useful for comparing files
- Closed all at once via **View → Close all tabs**

### SQLite / Database Viewer

Shows a table selector at the top. For databases opened from a live path, a **Summary** view lists all tables and their row counts.

| Control | Action |
|---|---|
| **Table** dropdown | Switch between tables |
| **Search** field | Filter visible rows — matches any column |
| **SQL** input | Run any `SELECT` query against the database |
| **Run** | Execute the SQL query |
| **Export CSV…** | Export the current view (filtered or query result) to a CSV file |

**Row limit notice:** if a table has more rows than the display limit, a notice appears in the row count. Use a SQL query with `LIMIT` / `WHERE` to load a specific subset.

**Timestamp column decoding:** right-click any column header to decode integer/real values as timestamps. Choose a format from the **Decode column as timestamp** submenu:

| Format | Epoch | Unit |
|---|---|---|
| Unix — seconds | 1970-01-01 | s |
| Unix — milliseconds | 1970-01-01 | ms |
| Unix — microseconds | 1970-01-01 | µs |
| Mac Absolute Time | 2001-01-01 | s |
| Windows FILETIME | 1601-01-01 | 100 ns |
| Chrome / WebKit | 1601-01-01 | µs |

Values are displayed as `YYYY-MM-DD HH:MM:SS UTC`. The column header shows the active format as a suffix (e.g. `created_at [unix ms]`). Sorting remains chronologically correct. Select **Clear timestamp format** to revert to the raw values.

**Cell inspection:** right-click any cell for options including:
- **Inspect Cell…** — preview the raw value, attempt base64/plist/XML decode
- **Open in Hex** — view cell bytes as hex
- **Open as new tab** — parse a BLOB cell as a new artifact (e.g. a plist stored inside a SQLite column)
- **Export…** — save the cell value to disk
- **Copy cell / Copy row / Copy selection**

### Hex Viewer

Displays raw bytes as offset + hex + ASCII. 256 KB is shown per page.

| Control | Action |
|---|---|
| **◀ Prev / Next ▶** | Navigate pages for files larger than 256 KB |
| **Page N / M** | Shows current position and total pages |
| **Search (ASCII)** | Find a text string — jumps to the correct page automatically |
| **Search (Hex)** | Find a byte pattern, e.g. `FF D8 FF` or `ffd8ff` |
| **Copy Hex** | Copy current page as space-separated hex bytes |
| **Copy ASCII** | Copy current page as ASCII (non-printable → `.`) |

### Text Viewer

Displays text files with line numbers, syntax highlighting, and search.

**Encoding detection** is automatic — the detected encoding is shown in the top-right corner of the toolbar. Supported: UTF-8, UTF-8 BOM, UTF-16 LE, UTF-16 BE, and UTF-16 LE without BOM (common in iOS preference files).

**Highlighting** is applied automatically based on content. You can override it with the **Highlight** dropdown: JSON, XML, SQL, INI/CONF, YAML, LOG, CSV, or None.

**Search:**
- Type in the search bar and matches are highlighted inline
- Use **Up / Down** to navigate between hits
- Enable **Regex** for regular expression patterns
- Enable **Case** for case-sensitive matching
- `*` wildcard is supported in non-regex mode

### Image Viewer

Displays JPEG, PNG, GIF, BMP, WebP, TIFF, and HEIC images. EXIF metadata (camera make/model, GPS coordinates, timestamp, ISO, aperture) is shown in the Properties panel when available.

### Media Viewer

Plays audio and video files (MP4, MOV, MP3, M4A, AAC, WAV, etc.) using the system multimedia backend.

### Plist / Tree Viewer

Displays binary and XML property lists as a collapsible tree. Supports nested structures including arrays, dictionaries, data blobs, dates, and NSKeyedArchiver objects.

### JSON Viewer

Displays JSON files as a collapsible, searchable tree. Arrays and objects can be expanded or collapsed individually. Copy a node value via right-click.

### XML Viewer

Parses XML into a collapsible tree. Android `<map>`-style preference files are flattened for easier reading. Malformed XML shows an error node rather than crashing.

### PDF Viewer

Extracts and displays the text content of PDF files in the Text Viewer. Scanned or protected PDFs with no extractable text show a notice.

### LevelDB Viewer

Opens LevelDB database directories (used by Chrome, Android apps, and iOS apps) and shows key-value records in a table. The first 2,000 records are displayed; use the search field to filter by key or value.

### ABX Viewer

Decodes Android Binary XML (ABX) format used in Android system and app settings directories.

### SEGB / Biome Viewer

Decodes Apple SEGB v1 and v2 files from the Biome framework. Shows timestamped records from app usage, screen time, Siri interaction, and location-adjacent signals.

### Realm Database Viewer

Opens `.realm` files in a tabbed view:

| Tab | Content |
|---|---|
| **Header** | File metadata decoded from the Realm file header |
| **Schema** | List of all classes/tables stored in the database |
| **Top Refs** | Comparison of top-ref pointers across header slots (useful for detecting corruption or versioning) |
| **Tables** | Column data for each table, displayed in the Table Viewer |
| **Hex Preview** | Raw hex of the first bytes of the file |

### Protobuf Viewer

Opens via right-click → **Open as Protobuf Viewer**. Performs a schema-less wire-format decode showing field numbers, wire types, and raw values.

To decode with a schema: click **Load .proto…** to load a `.proto` file, or **Load Descriptor…** for a compiled descriptor set. Field names and types are then resolved from the schema.

### Multi-Log Studio

A high-performance log viewer for large files and multi-source correlation. Open it via right-click → **Open in Multi-Log Studio**; add further files at any time with **Add to Multi-Log Studio** or the **+ Add Source** button inside the viewer.

**Toolbar filters** (apply across all sources simultaneously):

| Control | Action |
|---|---|
| Level buttons | Toggle ERROR / WARN / INFO / DEBUG / TRACE / UNKNOWN on or off |
| **Search** field | Filter by message, process, PID, subsystem, or category |
| **Format…** | Define or load a custom log format profile |

**Source bar** — one colour-coded chip per loaded file. Click a chip to hide or show that source. Chips scroll horizontally if many sources are loaded.

**Time-range filter** — appears after the first file with timestamps finishes loading. Check **Time range:** to enable the from/to pickers; **Reset** restores the full range. The **Display TZ** dropdown toggles between UTC and local time.

**Column filter inputs** — a persistent row of text fields above the log table, one per filterable column (Level, Process, PID, Subsystem, Category, Message). Type in any field to live-filter the table by a contains-match on that column. Multiple fields are AND-combined.

**Column filter bar** — appears below the toolbar when a right-click exact-value filter is active. Each active filter is shown as a chip (e.g. `subsystem = com.apple.security`). Click a chip's **×** to remove that filter, or **Clear all** to remove all at once.

**Detail panel** — selecting a row shows the raw original line(s). If the parser extracted extra fields (e.g. `subsystem`, `category`, `event_type`, `euid`, `thread_id` from Apple Unified Log entries), they appear below a separator.

**Apple Unified Log specifics** — `.tracev3` and `.logarchive` files are parsed via the bundled `unifiedlog_iterator` binary. Columns **Subsystem** and **Category** are populated directly. The detail panel also shows `event_type` (e.g. `logEvent`, `activityCreateEvent`, `lossEvent`), `euid`, `thread_id`, and `activity_id`. `lossEvent` entries — indicating missing log entries due to buffer overflow — are shown at WARN level with a descriptive message. `message_entries` of type Private or Sensitive are annotated `[private]` / `[sensitive]`; these may contain data that is redacted in live system logs but preserved in an offline acquisition.

**iOS full-filesystem acquisition** — right-clicking a `diagnostics/` directory (i.e. a node that contains `Persist/`, `timesync/`, `Special/`, or `Signpost/` as direct children) offers two additional actions:

- **Open in Multi-Log Studio** — Crush assembles a temporary logarchive from the diagnostics subtree and the sibling `uuidtext/` directory (needed for full message-string resolution), then converts all tracev3 files using parallel `unifiedlog_iterator` processes. Timestamps are correctly resolved as long as the acquisition includes `timesync/` files; if `timesync/` is absent or empty the Timestamp column will show "—".
- **Export as .logarchive…** — saves the assembled logarchive to a user-chosen folder so it can be examined in other tools (e.g. `log` on macOS).

**Parallel conversion** — when loading a `.logarchive` or iOS diagnostics directory, Crush splits the `Persist/*.tracev3` files across multiple `unifiedlog_iterator` processes (one per physical CPU core by default). Results appear in the viewer as each chunk finishes. The benchmark script `scripts/benchmark_unified_log.py` can be used to measure throughput and tune the worker count with `--workers N`.

**Context menu** (right-click any row):

| Option | Action |
|---|---|
| Copy message | Copies the parsed message text |
| Copy raw line | Copies the original unparsed line(s) |
| Copy selection (TSV) | Copies all selected rows as tab-separated values |
| Filter: [Column] = [value] | Pins an exact-match filter for the clicked cell; filter chip appears in the column filter bar |

**Custom format profiles**

For log files not auto-detected, click **Format…** to open the format dialog:

1. Enter a **Profile Name** and a **Parse Pattern** — a Python regex with named groups. The groups `timestamp`, `level`, `process`, `pid`, and `message` map to the corresponding columns; any other named group is stored as an extra field and shown in the detail panel.
2. Set **Timestamp Format** to a `strptime` string (e.g. `%d/%b/%Y:%H:%M:%S`). Leave empty to auto-detect ISO 8601 / epoch timestamps.
3. Optionally set **Line-Start Regex** to identify the first line of a multiline event (e.g. `^\d{4}-\d{2}-\d{2}`).
4. Optionally set **Level Map** as a JSON object to translate raw values to standard levels (e.g. `{"GET": "INFO", "500": "ERROR"}`).
5. The **Live Preview** panel highlights each named group in a distinct colour on the actual file content.
6. Click **Save Profile** to persist the profile for future use, then **Apply** to re-parse the selected source with this format.

Saved profiles are stored in `~/.config/crush/log_profiles/` and are available in the **Saved profiles** dropdown on the next start.

---

## Parsers & Viewers

Crush includes a growing set of parsers and viewers, with documented limitations for transparency. For the full, detailed list of what is supported and where the current gaps are, see `crush/docs/format-support.md`.

---

## Properties Panel

The right panel updates whenever you select or open a file. It shows:

- **File name and path**
- **MACB timestamps** — Modified, Accessed, Changed, Birth. Fields unavailable in the source format (ZIP and TAR only store mtime) are shown as **—** with an explanatory note
- **Format** — identified format name from the knowledge base (e.g. "SQLite Database", "Android Binary XML")
- **Forensic relevance** — what kind of data this format typically contains
- **Platforms** — which platforms this format originates from
- **Reference** — link to the format specification
- **Parser-specific metadata** — EXIF fields, page counts, parse errors, etc.

---

## Format Reference

**Help → Format Reference…** opens a searchable table of all formats known to Crush — both supported (with a parser) and unsupported (identified only).

- Supported formats appear in normal text
- Unsupported formats appear in grey — Crush will show forensic context in the Properties panel but display raw hex
- Select a row and click **Open Reference…** to open the format specification in your browser

---

## Exporting Files

Right-click any file or folder in the Filesystem panel and choose **Export…**. For folders, the entire subtree is exported preserving the directory structure.

---

## Paste & Decode

**Tools → Paste & Decode…** lets you paste raw binary data — copied from a hex editor, a SQLite BLOB cell, a network capture, or any other source — and open it directly in a Crush viewer without saving it to disk first.

1. Paste hex, base64, or plain text into the input area.
2. Set **Input encoding** to **Auto** (default) or force a specific encoding if auto-detection picks the wrong one.
3. Choose the target format from **Open as**:

| Open as | Notes |
|---|---|
| Auto-detect | Crush identifies the format by magic bytes |
| Binary plist (bplist) | Force the Property List viewer |
| XML / Text plist | Force the Property List viewer (XML form) |
| JSON | Force the JSON viewer |
| XML | Force the XML viewer |
| SQLite database | Force the SQLite / table viewer |
| Realm database | Force the Realm Database viewer |
| Android Binary XML (ABX) | Force the ABX viewer |
| SEGB / Biome | Force the SEGB viewer |
| Protobuf (schema-less) | Force the Protobuf wire decoder |
| Hex view (raw bytes) | Always open as raw hex, regardless of content |

4. The status line shows the decoded byte count as you type — if it stays grey, the input could not be decoded with the current encoding setting.
5. Click **Open** to open the data in a new viewer tab.

> **Tip:** Use this to inspect a BLOB that is not a supported type for automatic chaining — for example, paste a hex dump of a custom binary format and open it as raw hex to examine its structure.

---

## Integrity Mode

Integrity mode adds hashing and traceability to file access:

- When enabled, files opened or exported are hashed (SHA-256) and written to the log.
- Opening a ZIP/TAR/file triggers the calculation of the hash (SHA-256) of the file.
- Opening a folder does not hash the full directory.
- Exports also create a `crush-export-hashes.txt` file next to the exported data.
- The bottom-right status badge shows the current mode. Click the badge to toggle it, or right-click it for a quick menu and a short explanation.

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Q` | Quit |
| `Ctrl+F` | Focus the search bar in the Text viewer (when a text tab is active) |
| Middle-click tab | Close tab |

---

## Tips for Forensic Workflows

- **Large archives:** Crush loads ZIP and TAR indexes immediately and reads file content on demand — you do not need to wait for a full extraction before browsing.
- **SQLite WAL files:** if a `-wal` or `-shm` companion file is present alongside a `.db`, Crush automatically includes it so you see the most recent state of the database including committed transactions not yet checkpointed into the main database file.
- **BLOB chaining:** SQLite cells containing embedded plists, images, or other binary data can be opened directly as a new viewer tab via right-click → **Open as new tab**.
- **Unknown files:** even if Crush cannot parse a file, the Properties panel will show the identified format name and forensic relevance based on magic bytes — so you know what you are looking at before deciding to export and open it externally.

---

## Bugs and feature requests

Found a bug or have a suggestion? Open an issue on [GitHub](https://github.com/kalink0/crush-forensics/issues). Please include the Crush version (shown in **Help → About**), your OS, and steps to reproduce.
