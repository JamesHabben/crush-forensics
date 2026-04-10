# Multi-Log Studio — Planning Document

**Status:** Planning  
**Created:** 2026-04-10  
**Components:** `crush/viewers/multi_log_viewer.py` (new), `crush/parsers/multi_log_parser.py` (new)

---

## Motivation

The existing `LogViewer` is designed for single files and loads all entries synchronously into a
`QStandardItemModel`. This causes noticeable sluggishness with large log files (>50k entries), because
Qt allocates a separate `QStandardItem` object for every cell, and the proxy filter evaluates every
row individually on each keystroke.

Additionally, there is no way to view multiple log sources simultaneously in a shared timeline — a
common forensics scenario (e.g. correlating Syslog + App Log + Auth Log at the same time).

The existing `LogViewer` remains unchanged for the single-file use case.

---

## Goals

1. **Speed** — 200k+ entries loadable and filterable without affecting Crush's startup time.
2. **Multi-Source** — Multiple log files open simultaneously in a shared, timestamp-sorted timeline.
3. **Custom Formats** — Unknown log types definable via regex + strptime; fields mappable to the internal standard model.
4. **Unified Search** — Text, level, and time-range filters apply across all loaded sources at once.
5. **Isolated Entry Point** — Opened explicitly via "Open in Multi-Log Studio" (no auto-detect, no impact on existing viewers).

---

## Architecture

### Internal Data Model (Standard Fields)

Every normalised log entry is a Python `dict` with these fields:

| Field       | Type             | Description                                    |
|-------------|------------------|------------------------------------------------|
| `timestamp` | `datetime\|None` | UTC-normalised                                 |
| `level`     | `str`            | `ERROR / WARN / INFO / DEBUG / TRACE / UNKNOWN`|
| `process`   | `str`            | Tag, process name, logger name, etc.           |
| `message`   | `str`            | Primary message (may be multiline)             |
| `raw`       | `str`            | Original line(s) for copy/export               |
| `source`    | `str`            | Filename of the source                         |
| `source_id` | `int`            | Internal source index (used for colour/filter) |

All parser results (JSON Lines, logcat, Syslog, Generic, Custom) are mapped to this model.

### Virtual Qt Model

Instead of `QStandardItemModel`, a custom `QAbstractTableModel` that references the Python list directly:

```
Now:  Python-List → QStandardItem × (rows × cols) → Proxy → View
New:  Python-List (stays in RAM) → MultiLogModel(QAbstractTableModel) → View
```

- `data()` reads directly from the Python list — no Qt object overhead.
- Filtering = a separate `list[int]` holding the indices of visible rows.
- On filter change: rebuild the index list in Python (fast), then `beginResetModel()` / `endResetModel()`.
- For very large datasets: chunk-based rebuilding via `QTimer` to keep the UI responsive.

### Background Loading

```
Main Thread                     Worker Thread (QThread)
     |                                  |
     | — start_worker(path) --------->  |
     |                                  | — parse chunk 1 (5,000 entries)
     | <— chunk_ready(entries) -------- |
     | — append to model                |
     |                                  | — parse chunk 2
     | <— chunk_ready(entries) -------- |
     | — append to model                |
     |                                  | — emit finished()
     | <— finished() ------------------ |
     | — sort & rebuild filter index    |
```

- Parser emits chunks (default: 5,000 entries).
- UI shows first results immediately while the rest is loading.
- Crush startup time is not affected — the worker only starts when the tab is opened.
- Progress indicator in the viewer's status bar (entries loaded / file %).

### Multi-Source UI

```
┌──────────────────────────────────────────────────────────────────┐
│  [+ Add Source]  [● system.log]  [● app.log]  [● auth.log]       │
├──────────────────────────────────────────────────────────────────┤
│  Source    │ Timestamp          │ Level │ Process │ Message       │
│  system    │ 2026-04-10 12:01  │ ERROR │ sshd    │ Failed ...    │
│  app       │ 2026-04-10 12:01  │ INFO  │ api     │ Request ...   │
│  auth      │ 2026-04-10 12:02  │ WARN  │ pam     │ Unknown ...   │
└──────────────────────────────────────────────────────────────────┘
```

- Each source has a distinct accent colour (shown in the source chip and the Source column).
- Source chips: click to toggle individual sources on/off.
- Shared timeline: all entries merged and sorted by `timestamp` (entries without timestamp appended at the end).
- "Add Source" button opens a file dialog; the source is loaded in the background and inserted into the existing timeline.

### Custom Format Definition

Dialog "Define Log Format" (accessible via a "Format…" button in the viewer):

**Fields:**
- **Name** — free-form profile name (e.g. "Nginx Access Log")
- **Line-Start Pattern** — regex that identifies the start of a new event (used for multiline grouping)
- **Parse Pattern** — regex with named groups:
  - `(?P<timestamp>...)` → timestamp field
  - `(?P<level>...)` → level field
  - `(?P<process>...)` → process field
  - `(?P<message>...)` → message field
- **Timestamp Format** — Python `strptime` format string (e.g. `%d/%b/%Y:%H:%M:%S`)
- **Level Map** — optional translation table (e.g. `{"GET": "INFO", "500": "ERROR"}`)

**Live Preview:**  
While typing, the first 10 lines of the currently open file are tested against the pattern;
matched fields are highlighted in colour.

**Persistence:**  
Profiles are saved as JSON in `~/.config/crush/log_profiles/` and loaded automatically on next start.

Example profile:
```json
{
  "name": "Nginx Access Log",
  "line_start_pattern": "^\\d{1,3}\\.\\d{1,3}",
  "parse_pattern": "(?P<process>\\S+) .+ \\[(?P<timestamp>[^\\]]+)\\] \"(?P<message>[^\"]+)\" (?P<level>\\d{3})",
  "timestamp_format": "%d/%b/%Y:%H:%M:%S %z",
  "level_map": {"200": "INFO", "201": "INFO", "301": "INFO", "302": "INFO",
                "400": "WARN", "403": "WARN", "404": "WARN",
                "500": "ERROR", "502": "ERROR", "503": "ERROR"},
  "level_default": "INFO"
}
```

---

## Implementation Plan (Phases)

### Phase 1 — Virtual Model + Fast Filtering
- Implement `MultiLogModel(QAbstractTableModel)`
- Filtering via `list[int]` (index list instead of proxy row iteration)
- Use existing parser output as data source
- **Result:** Single file, but ~10× faster than the current viewer

### Phase 2 — Background Loading
- `LogLoaderWorker(QThread)` with chunk signals
- Progress indicator in the viewer
- Progressive insertion into the model
- **Result:** UI stays responsive when opening large files

### Phase 3 — Multi-Source
- Manage multiple sources in the model (per source: list + metadata)
- Source chip bar in the toolbar
- Merged, sorted timeline
- "Add Source" action (from toolbar + VFS tree context menu)
- **Result:** Correlation of multiple log files possible

### Phase 4 — Custom Format Dialog
- "Define Format" dialog with regex editor and live preview
- `CustomFormatParser` using named-group regex + strptime
- Profile management (save / load / delete)
- Profile selection when opening an unrecognised format
- **Result:** Arbitrary log formats analysable

---

## Distinction from the Existing Log Viewer

| Aspect               | Existing `LogViewer`          | Multi-Log Studio              |
|----------------------|-------------------------------|-------------------------------|
| Entry point          | Right-click → "Open as Log"   | Right-click → "Multi-Log Studio" |
| Sources              | 1 file                        | N files                       |
| Qt model             | QStandardItemModel            | QAbstractTableModel (virtual) |
| Loading              | Synchronous, blocking         | Async, chunk-based            |
| Custom formats       | No                            | Yes, with profile persistence |
| Target file size     | Small / medium logs           | Arbitrarily large             |

---

## Open Questions

- [ ] Should the Multi-Log Studio tab get its own dock window, or be embedded in the existing tab area?
- [ ] Should there be an export function (filtered results as CSV / JSON)?
- [ ] Time-axis slider as a visual timeline (planned for Log Viewer iteration 2 — useful here too)?
- [ ] Cap the number of simultaneous sources (UX) or leave it unlimited?
