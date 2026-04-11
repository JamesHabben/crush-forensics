# Multi-Log Studio — Planning Document

**Status:** Phase 5 complete  
**Created:** 2026-04-10  
**Components:** `crush/viewers/multi_log_viewer.py`, `crush/parsers/multi_log_parser.py`

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

| Field       | Type                  | Description                                          |
|-------------|-----------------------|------------------------------------------------------|
| `timestamp` | `datetime\|None`      | UTC-normalised                                       |
| `level`     | `str`                 | `ERROR / WARN / INFO / DEBUG / TRACE / UNKNOWN`      |
| `process`   | `str`                 | Process name, logger name, tag, etc.                 |
| `pid`       | `str`                 | Process ID — empty string if unavailable             |
| `message`   | `str`                 | Primary message (may be multiline)                   |
| `raw`       | `str`                 | Original line(s) for copy/export                     |
| `source`    | `str`                 | Filename of the source                               |
| `source_id` | `int`                 | Internal source index (used for colour/filter)       |
| `extra`     | `dict[str, str]`      | Parser-specific fields not covered by the above      |

`extra` is the extension point for formats with richer metadata — all fields that
don't map to a standard column go here.  The detail panel shows them; the search
bar matches against their values.

Typical `extra` keys per format:

| Format            | Keys in `extra`                                              |
|-------------------|--------------------------------------------------------------|
| Apple Unified Log | `subsystem`, `category`, `thread_id`, `activity_id`, `sender` |
| Syslog            | `facility`                                                   |
| Android logcat    | `thread_id`                                                  |
| Custom (Phase 4)  | any named group not mapped to a standard field               |

All parser results (JSON Lines, logcat, Syslog, Generic, Custom, Apple UL) are mapped to this model.

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

### Phase 1 — Virtual Model + Fast Filtering ✓ (2026-04-10)
- `MultiLogModel(QAbstractTableModel)` in `crush/viewers/multi_log_viewer.py`
- Filtering via `_visible: list[int]` (subsequence of `_sort_order`)
- Sorting implemented directly on the model via `sort()` — no proxy needed
- Entry point: right-click → "Open in Multi-Log Studio" → `"multi_log"` viewer type
- **Result:** Single file, virtual model, ~10× less memory than QStandardItemModel

### Phase 2 — Background Loading ✓ (2026-04-10)
- `LogLoaderWorker(QThread)` — runs `LogParser.parse()` off the main thread, emits `chunk_ready(list)` in batches of 5,000 entries, then `load_finished(str, dict)`
- `MultiLogModel.append_chunk()` — uses `beginInsertRows`/`endInsertRows` (no full reset per chunk)
- `MultiLogModel.finalize_sort()` — applies full sort once after all chunks arrive
- 4 px indeterminate `QProgressBar` in the viewer; hidden on `load_finished`
- Time bar initialised and shown only after `load_finished` confirms timestamps exist
- Sorting disabled on the table during loading; re-enabled after `finalize_sort()`
- `MultiLogViewer` constructor changed to `(node, vfs, parent)` — viewer owns the worker
- **Result:** UI stays responsive; tab opens immediately, entries appear as chunks arrive

### Phase 3 — Multi-Source ✓ (2026-04-10)
- `LogLoaderWorker` extended: carries `source_id` in all signals
- `MultiLogModel`: source registry (`register_source`, `set_source_visible`, `source_color`);
  `append_chunk(source_id, entries)` stamps each entry; source filter in `_apply_filter()`
- New columns: **Source** (coloured by source accent), **PID**
- Text search extended to `extra` fields (subsystem, category, etc.)
- `MultiLogViewer.add_source(node, vfs)` — public API to add a source programmatically
- Source chip bar: scrollable row of colour-coded toggle buttons, one per source
- "Add Source" button: opens `QFileDialog`, loads via `FileVFS`
- VFS tree: "Add to Multi-Log Studio" → routes to active/most-recent open studio tab;
  falls back to opening a new tab if none is open
- `_find_multi_log_viewer()` in `main_window`: checks active tab first, then scans
  tab list in reverse; handles always-hex wrapper transparently
- **Result:** Correlation of multiple log files in a shared timeline

### Phase 5 — Folder Log Discovery ✓ (2026-04-11)
- Right-click a folder in the VFS tree → "Open Logs in Multi-Log Studio"
- Recursively walk the VFS subtree; probe each file with a fast heuristic:
  - Known log extensions (`.log`, `.txt`, `.json`, `.jsonl`) **or**
  - `LogParser` peek on first 40 lines — accept if any format scores ≥ 2 hits
- Confirmation dialog before loading: "Found 23 log files — open all?" with a
  checklist so the user can deselect individual files
- Feed accepted files into the existing multi-source pipeline (Phase 3) one by one,
  each in its own background worker (Phase 2)
- **Dependencies:** Phase 2 (background loading) + Phase 3 (multi-source) must be complete
- **Result:** Entire log folder analysable in one action
- **Implementation:** `_probe_is_log()` / `_discover_log_nodes()` / `FolderDiscoveryDialog`
  in `multi_log_viewer.py`; `"multi_log_folder"` mode wired in `fs_panel.py` +
  `main_window.py`
- **Architecture change (post-phase):** Multi-Log Studio moved from embedded tab to
  standalone OS window (`Qt.Window` flag, parented to MainWindow). Sizing: 80% of
  available screen geometry, capped at 1400×850. Toolbar uses `setMaximumWidth` /
  `Expanding` policy instead of fixed widths so the window is freely resizable.

### Phase 4 — Custom Format Dialog ✓ (2026-04-10)
- `CustomFormatProfile` dataclass + `ProfileManager` (save/load/delete JSON profiles
  in `~/.config/crush/log_profiles/`) in `crush/parsers/multi_log_parser.py`
- `CustomFormatParser` — named-group regex + strptime, multiline grouping,
  level_map translation; `extra` dict for non-standard groups
- `DefineFormatDialog` in `multi_log_viewer.py` — profile list, editor fields,
  live regex preview with colour-coded group highlighting (300 ms debounce)
- `LogLoaderWorker` extended: `profile` parameter routes to `CustomFormatParser`
  instead of `LogParser`; `cancel()` / `_cancel_flag` for clean reload
- `MultiLogModel.replace_source_entries()` — clears one source and resets indices
  so a reload worker can refill it cleanly via `append_chunk`
- `MultiLogModel.preview_lines_for_source()` — raw lines from loaded entries
  (no file re-read needed for preview)
- "Format…" button in toolbar opens the dialog; *Apply* triggers
  `reload_source_with_profile()` which cancels the old worker and starts a new one
- **Result:** Arbitrary log formats analysable; profiles persist across sessions

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
