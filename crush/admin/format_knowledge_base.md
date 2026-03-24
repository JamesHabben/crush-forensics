# Format Knowledge Base — Admin Guide

## Overview

Crush maintains a bundled format knowledge base that identifies file formats and surfaces forensic context in the UI — even for formats that have no parser yet.

There is **one source of truth**: `crush/data/build_formats_db.py`.
Everything else is generated from it.

```
crush/data/build_formats_db.py   ← edit this
crush/data/formats.db            ← generated artifact (commit both)
crush/core/format_db.py          ← runtime wrapper (do not edit for data changes)
```

---

## Adding or Editing a Format

Open `crush/data/build_formats_db.py` and find the `FORMATS` list. Each entry is a plain Python dict:

```python
{
    "name": "SQLite Database",           # Full human-readable name shown in UI
    "short_name": "SQLite",              # Abbreviation
    "category": "database",             # See Categories below
    "forensic_relevance": "...",         # What an investigator finds here
    "platforms": "iOS,macOS,Android",   # Comma-separated, no spaces
    "parser_class": "SQLiteParser",     # Class name in crush/parsers/, or None
    "magic": [(0, b"SQLite format 3\x00")],  # List of (offset, bytes) tuples
    "extensions": [".db", ".sqlite"],   # Lowercase with dot
    "docs_url": "https://...",          # Reference link (opens from Format Reference dialog)
},
```

After editing, regenerate the database:

```bash
python -m crush.data.build_formats_db
```

Commit **both** `build_formats_db.py` and `formats.db`.

---

## Fields Reference

| Field | Required | Notes |
|---|---|---|
| `name` | Yes | Shown in Properties panel and Format Reference dialog |
| `short_name` | No | Abbreviation for compact display |
| `category` | No | See Categories below |
| `forensic_relevance` | No | Shown in Properties panel — explain what an analyst finds here |
| `platforms` | No | `iOS`, `macOS`, `Android`, `Windows`, `Cross-platform` — comma-separated |
| `parser_class` | No | Class name of the Crush parser, e.g. `"SQLiteParser"`. `None` = unsupported |
| `magic` | No | List of `(offset, bytes)` tuples — **all** must match for a hit |
| `extensions` | No | Fallback when no magic matches. Lowercase, include the dot |
| `docs_url` | No | Opened by "Open Reference…" button in Format Reference dialog |

### Categories

| Value | Used for |
|---|---|
| `database` | SQLite, LevelDB, Core Data |
| `plist` | Binary and XML plists, NSKeyedArchiver |
| `image` | JPEG, PNG, HEIC, etc. |
| `media` | MP4, MP3, etc. |
| `archive` | ZIP, TAR, DMG, sparse images |
| `log` | Unified Log, SEGB/Biome, EVTX, crash reports |
| `serialization` | Protobuf, MessagePack, CBOR |
| `executable` | DEX, OAT, Mach-O, ELF |
| `crypto` | Keychain, encrypted containers |
| `other` | XML, JSON, PDF, anything else |

---

## Adding a Format with No Parser

If you want Crush to identify a file and show forensic context without parsing it, set `parser_class: None`. The hex fallback will show the format name, platforms, and forensic relevance in the Properties panel automatically.

```python
{
    "name": "iOS Unified Log (tracev3)",
    "short_name": "tracev3",
    "category": "log",
    "forensic_relevance": "System and app logs since iOS 10 ...",
    "platforms": "iOS,macOS",
    "parser_class": None,
    "magic": [(0, b"\x30\x74\x72\x33")],
    "extensions": [".tracev3"],
    "docs_url": "https://github.com/mandiant/macos-UnifiedLogs",
},
```

---

## Adding a Format with a New Parser

1. Write the parser in `crush/parsers/your_parser.py` (subclass `AbstractParser`)
2. Register it in `crush/parsers/__init__.py`
3. Add an entry to `FORMATS` in `build_formats_db.py` with `"parser_class": "YourParser"`
4. Run `python -m crush.data.build_formats_db`

The parser carries **no metadata** — all format knowledge lives in `build_formats_db.py`.

---

## Upgrading an Unsupported Format to Supported

Find the existing entry and set `parser_class` to the new parser class name:

```python
# Before
"parser_class": None,

# After
"parser_class": "TraceV3Parser",
```

Then rebuild the DB. No other files need to change.

---

## How Identification Works at Runtime

1. **Magic bytes** — checked first. All `(offset, pattern)` pairs in an entry must match.
2. **Extension** — fallback when no magic entry matches.
3. **Parser class lookup** — when a file is successfully parsed, `FormatDatabase.by_parser_class()` looks up the format by the parser's class name, bypassing magic/extension detection entirely.

For **unsupported files** (handled by `HexFallbackParser`), magic + extension identification runs and the result is shown in the Properties panel alongside the raw hex view.

---

## Format Reference Dialog

**Help → Format Reference…** opens a searchable table of all formats in `formats.db`.

- Supported formats (with a parser) are shown in normal text.
- Unsupported formats are shown in grey.
- Selecting a row and clicking **Open Reference…** opens the `docs_url` in the system browser.
