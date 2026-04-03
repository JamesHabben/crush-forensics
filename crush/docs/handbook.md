# Crush — User Handbook

## What is Crush?

Crush is a Digital Forensic Analysis Workbench for examining iOS and Android acquisitions. It lets you open archives (ZIP, TAR), folders, and individual files, then navigate and inspect their contents using format-aware viewers — without extracting anything to disk first.

Crush includes a built-in **file format database** covering forensically relevant formats across iOS and Android. For every file you select or open, Crush identifies the format by magic bytes (not by extension), then shows its name, platform, forensic relevance, and a link to the format specification — even for formats that have no dedicated viewer yet. - the database in work in progress - more info and more file formats to come.

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

### ABX Viewer

Decodes Android Binary XML (ABX) format used in Android system and app settings directories.

### SEGB / Biome Viewer

Decodes Apple SEGB v1 and v2 files from the Biome framework. Shows timestamped records from app usage, screen time, Siri interaction, and location-adjacent signals.

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

## Forensic Mode

Forensic mode adds hashing and traceability to file access:

- When enabled, files opened or exported are hashed (SHA-256) and written to the log.
- Opening a ZIP/TAR/file source hashes the entire source file and logs the result.
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
