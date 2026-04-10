# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Multi-Log Studio viewer — Phase 3: multiple sources, merged timeline.

Architecture:
  LogLoaderWorker (QThread)  — reads + parses a VFS node off the main thread,
                               emits results in chunks of CHUNK_SIZE entries.
                               Carries source_id in every signal.
  MultiLogModel              — QAbstractTableModel backed by a plain Python list;
                               accepts chunks via append_chunk() using
                               beginInsertRows/endInsertRows (no full reset per chunk).
                               Supports N simultaneous sources; each source has a
                               colour and can be toggled on/off independently.
  MultiLogViewer             — widget that owns N workers and one model; shows an
                               indeterminate progress bar while any worker is loading.
                               "Add Source" button / public add_source() method.

Entry dict schema (standard fields — all parsers must map to these):
    timestamp  : datetime | None   — UTC-normalised
    level      : str               — ERROR / WARN / INFO / DEBUG / TRACE / UNKNOWN
    process    : str               — process name, logger name, tag, etc.
    pid        : str               — process ID (empty string if unavailable)
    message    : str               — primary message (may be multiline)
    raw        : str               — original line(s) for copy / export
    source     : str               — filename of the source
    source_id  : int               — internal source index
    extra      : dict[str, str]    — parser-specific fields not covered above
                                     (e.g. subsystem, category, thread_id,
                                      activity_id, facility, sender for Apple UL)
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone, tzinfo
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QDateTime,
    QModelIndex,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from crush.core.vfs import VFS, VFSNode

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LEVELS = ["ERROR", "WARN", "INFO", "DEBUG", "TRACE", "UNKNOWN"]

_LEVEL_COLORS: dict[str, QColor] = {
    "ERROR":   QColor("#c0392b"),
    "WARN":    QColor("#e67e22"),
    "INFO":    QColor("#2980b9"),
    "DEBUG":   QColor("#7f8c8d"),
    "TRACE":   QColor("#95a5a6"),
    "UNKNOWN": QColor("#bdc3c7"),
}

# Source accent colours — cycled as sources are added
_SOURCE_COLORS: list[QColor] = [
    QColor("#2980b9"),
    QColor("#27ae60"),
    QColor("#8e44ad"),
    QColor("#e67e22"),
    QColor("#16a085"),
    QColor("#c0392b"),
    QColor("#f39c12"),
    QColor("#2c3e50"),
]

# Column indices
_COL_SRC  = 0
_COL_TS   = 1
_COL_LVL  = 2
_COL_PROC = 3
_COL_PID  = 4
_COL_MSG  = 5

_HEADERS = ["Source", "Timestamp", "Level", "Process / Tag", "PID", "Message"]

# Custom data roles
_ROLE_TS_DT    = Qt.ItemDataRole.UserRole + 1   # datetime | None
_ROLE_LEVEL    = Qt.ItemDataRole.UserRole + 2   # str
_ROLE_RAW      = Qt.ItemDataRole.UserRole + 3   # str (original lines)
_ROLE_MSG_FULL = Qt.ItemDataRole.UserRole + 4   # str (full message, may be multiline)


def _fmt_ts(dt: datetime | None, tz: tzinfo = timezone.utc) -> str:
    if dt is None:
        return "—"
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")


def _msg_display(msg: str) -> str:
    if "\n" in msg:
        lines = msg.split("\n")
        n = len(lines) - 1
        return f"{lines[0]}  [{n} more line{'s' if n > 1 else ''}]"
    return msg


# Colours used in the live-preview to highlight named regex groups
_PREVIEW_GROUP_COLORS: dict[str, str] = {
    "timestamp": "#3498db",
    "level":     "#e67e22",
    "process":   "#27ae60",
    "pid":       "#9b59b6",
    "message":   "#bdc3c7",
}
_PREVIEW_EXTRA_COLOR = "#1abc9c"


# ---------------------------------------------------------------------------
# Define Format dialog (Phase 4)
# ---------------------------------------------------------------------------

class DefineFormatDialog(QDialog):
    """Dialog for defining and managing custom log format profiles.

    Opened via the 'Format…' button in MultiLogViewer's toolbar.

    After the user clicks *Apply*:
      - ``result_profile()``    returns the active ``CustomFormatProfile``
      - ``result_source_id()``  returns the source_id to re-parse

    The dialog has a live preview that highlights named groups in the
    raw text as the user edits the pattern (debounced, 300 ms).
    """

    PREVIEW_LINES   = 20
    PREVIEW_DELAY   = 300   # ms

    def __init__(
        self,
        preview_lines: list[str],
        sources: list[tuple[int, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Define Log Format — Multi-Log Studio")
        self.setMinimumSize(840, 660)

        self._preview_lines = preview_lines[: self.PREVIEW_LINES]
        self._sources       = sources
        self._result_profile: Any = None
        self._result_source_id: int = sources[0][0] if sources else 0

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._refresh_preview)

        self._build_ui()
        self._reload_profiles_combo()
        self._schedule_preview()

    # ------------------------------------------------------------------
    # Results (read after exec() returns Accepted)
    # ------------------------------------------------------------------

    def result_profile(self) -> Any:
        return self._result_profile

    def result_source_id(self) -> int:
        return self._result_source_id

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        # ---- Saved-profiles bar ----
        saved_row = QHBoxLayout()
        saved_row.addWidget(QLabel("Saved profiles:"))
        self._profiles_combo = QComboBox()
        self._profiles_combo.setMinimumWidth(220)
        saved_row.addWidget(self._profiles_combo)
        load_btn = QPushButton("Load")
        load_btn.setFixedWidth(64)
        load_btn.clicked.connect(self._on_load_profile)
        saved_row.addWidget(load_btn)
        del_btn = QPushButton("Delete")
        del_btn.setFixedWidth(64)
        del_btn.clicked.connect(self._on_delete_profile)
        saved_row.addWidget(del_btn)
        saved_row.addStretch()
        root.addLayout(saved_row)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ---- Form ----
        form_outer = QWidget()
        form = QFormLayout(form_outer)
        form.setSpacing(6)
        form.setContentsMargins(0, 0, 0, 0)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Nginx Access Log")
        form.addRow("Profile Name:", self._name_edit)

        self._pattern_edit = QLineEdit()
        self._pattern_edit.setPlaceholderText(
            r"(?P<timestamp>\S+) (?P<level>\w+) (?P<process>[^:]+): (?P<message>.*)"
        )
        self._pattern_edit.textChanged.connect(self._schedule_preview)
        form.addRow("Parse Pattern:", self._pattern_edit)

        hint = QLabel(
            "Named groups → columns: "
            "<b>timestamp</b> · <b>level</b> · <b>process</b> · "
            "<b>pid</b> · <b>message</b> — any other group → <i>extra</i> field."
        )
        hint.setWordWrap(True)
        form.addRow("", hint)

        self._ts_fmt_edit = QLineEdit()
        self._ts_fmt_edit.setPlaceholderText(
            "%Y-%m-%d %H:%M:%S  (empty = auto-detect ISO / epoch)"
        )
        self._ts_fmt_edit.textChanged.connect(self._schedule_preview)
        form.addRow("Timestamp Format:", self._ts_fmt_edit)

        self._line_start_edit = QLineEdit()
        self._line_start_edit.setPlaceholderText(
            r"^\d{4}-\d{2}-\d{2}  (optional — marks start of multiline events)"
        )
        self._line_start_edit.textChanged.connect(self._schedule_preview)
        form.addRow("Line-Start Regex:", self._line_start_edit)

        self._level_map_edit = QLineEdit()
        self._level_map_edit.setPlaceholderText(
            '{"GET":"INFO","POST":"INFO","500":"ERROR"}  (optional JSON)'
        )
        self._level_map_edit.textChanged.connect(self._schedule_preview)
        form.addRow("Level Map:", self._level_map_edit)

        self._default_level_combo = QComboBox()
        for lvl in ["UNKNOWN", "INFO", "DEBUG", "WARN", "ERROR", "TRACE"]:
            self._default_level_combo.addItem(lvl)
        self._default_level_combo.currentTextChanged.connect(self._schedule_preview)
        form.addRow("Default Level:", self._default_level_combo)

        splitter.addWidget(form_outer)

        # ---- Preview ----
        prev_outer = QWidget()
        prev_layout = QVBoxLayout(prev_outer)
        prev_layout.setContentsMargins(0, 4, 0, 0)
        prev_layout.setSpacing(4)

        legend_row = QHBoxLayout()
        legend_row.addWidget(QLabel(f"Live preview (first {self.PREVIEW_LINES} lines):"))
        legend_parts = " · ".join(
            f"<span style='color:{c};'>{g}</span>"
            for g, c in _PREVIEW_GROUP_COLORS.items()
        ) + f" · <span style='color:{_PREVIEW_EXTRA_COLOR};'>extra</span>"
        legend_lbl = QLabel(legend_parts)
        legend_row.addStretch()
        legend_row.addWidget(legend_lbl)
        prev_layout.addLayout(legend_row)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        font = self._preview.font()
        font.setFamily("monospace")
        font.setPointSize(10)
        self._preview.setFont(font)
        self._preview.setStyleSheet("background-color:#1a1a2e; color:#e0e0e0;")
        prev_layout.addWidget(self._preview)

        splitter.addWidget(prev_outer)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter)

        # ---- Bottom buttons ----
        btn_row = QHBoxLayout()
        btn_row.addWidget(QLabel("Apply to source:"))
        self._source_combo = QComboBox()
        for sid, name in self._sources:
            self._source_combo.addItem(name, sid)
        btn_row.addWidget(self._source_combo)
        btn_row.addStretch()

        save_btn = QPushButton("Save Profile")
        save_btn.clicked.connect(self._on_save_profile)
        btn_row.addWidget(save_btn)

        apply_btn = QPushButton("Apply")
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(apply_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------

    def _reload_profiles_combo(self) -> None:
        from crush.parsers.multi_log_parser import ProfileManager
        self._profiles_combo.clear()
        self._profiles_combo.addItem("— select a saved profile —", None)
        for p in ProfileManager.all():
            self._profiles_combo.addItem(p.name, p)

    def _on_load_profile(self) -> None:
        profile = self._profiles_combo.currentData()
        if profile is not None:
            self._populate_fields(profile)

    def _on_delete_profile(self) -> None:
        profile = self._profiles_combo.currentData()
        if profile is None:
            return
        from crush.parsers.multi_log_parser import ProfileManager
        ProfileManager.delete(profile.name)
        self._reload_profiles_combo()

    def _on_save_profile(self) -> None:
        profile = self._build_profile()
        if profile is None:
            return
        from crush.parsers.multi_log_parser import ProfileManager
        ProfileManager.save(profile)
        self._reload_profiles_combo()

    def _on_apply(self) -> None:
        profile = self._build_profile()
        if profile is None:
            return
        self._result_profile = profile
        sid = self._source_combo.currentData()
        if sid is not None:
            self._result_source_id = sid
        self.accept()

    # ------------------------------------------------------------------
    # Field helpers
    # ------------------------------------------------------------------

    def _populate_fields(self, profile: Any) -> None:
        self._name_edit.setText(profile.name)
        self._pattern_edit.setText(profile.parse_pattern)
        self._ts_fmt_edit.setText(profile.timestamp_format)
        self._line_start_edit.setText(profile.line_start_pattern)
        lm_str = json.dumps(profile.level_map) if profile.level_map else ""
        self._level_map_edit.setText(lm_str)
        idx = self._default_level_combo.findText(profile.level_default)
        if idx >= 0:
            self._default_level_combo.setCurrentIndex(idx)

    def _build_profile(self) -> Any:
        from crush.parsers.multi_log_parser import CustomFormatProfile
        name    = self._name_edit.text().strip()
        pattern = self._pattern_edit.text().strip()
        if not name or not pattern:
            return None
        try:
            re.compile(pattern)
        except re.error:
            return None
        level_map: dict[str, str] = {}
        lm_text = self._level_map_edit.text().strip()
        if lm_text:
            try:
                level_map = json.loads(lm_text)
            except (json.JSONDecodeError, ValueError):
                pass
        line_start = self._line_start_edit.text().strip()
        if line_start:
            try:
                re.compile(line_start)
            except re.error:
                line_start = ""
        return CustomFormatProfile(
            name=               name,
            parse_pattern=      pattern,
            timestamp_format=   self._ts_fmt_edit.text().strip(),
            line_start_pattern= line_start,
            level_map=          level_map,
            level_default=      self._default_level_combo.currentText(),
        )

    # ------------------------------------------------------------------
    # Live preview
    # ------------------------------------------------------------------

    def _schedule_preview(self) -> None:
        self._preview_timer.start(self.PREVIEW_DELAY)

    def _refresh_preview(self) -> None:
        if not self._preview_lines:
            self._preview.setPlainText("(no preview content)")
            return

        pattern = self._pattern_edit.text().strip()
        if not pattern:
            raw_block = "<br>".join(html.escape(ln) for ln in self._preview_lines)
            self._preview.setHtml(
                f"<pre style='color:#888;'>"
                f"(enter a parse pattern to see matches)<br><br>"
                f"{raw_block}</pre>"
            )
            return

        try:
            rx = re.compile(pattern)
        except re.error as exc:
            self._preview.setHtml(
                f"<pre style='color:#e74c3c;'>"
                f"Invalid regex: {html.escape(str(exc))}</pre>"
            )
            return

        rows: list[str] = []
        for i, line in enumerate(self._preview_lines, 1):
            m = rx.search(line)
            if m:
                rows.append(self._colorize_line(i, line, m))
            else:
                rows.append(
                    f"<div style='padding:1px 4px;'>"
                    f"<span style='color:#7f8c8d;'>{i:3d}</span> "
                    f"<span style='color:#e74c3c;'>✗</span> "
                    f"<span style='color:#666;'>{html.escape(line)}</span>"
                    f"</div>"
                )

        self._preview.setHtml(
            "<div style='font-family:monospace;font-size:10pt;'>"
            + "".join(rows)
            + "</div>"
        )

    @staticmethod
    def _colorize_line(line_num: int, line: str, m: re.Match) -> str:  # type: ignore[type-arg]
        """Return an HTML row with each named group highlighted."""
        spans: list[tuple[int, int, str]] = []
        for name in m.groupdict():
            try:
                start, end = m.span(name)
            except IndexError:
                continue
            if start < 0:
                continue
            color = _PREVIEW_GROUP_COLORS.get(name, _PREVIEW_EXTRA_COLOR)
            spans.append((start, end, color))
        spans.sort(key=lambda x: x[0])

        # Drop overlapping spans (keep first)
        merged: list[tuple[int, int, str]] = []
        for span in spans:
            if merged and span[0] < merged[-1][1]:
                continue
            merged.append(span)

        parts: list[str] = []
        pos = 0
        for start, end, color in merged:
            if pos < start:
                parts.append(
                    f"<span style='color:#bdc3c7;'>{html.escape(line[pos:start])}</span>"
                )
            parts.append(
                f"<span style='color:{color};font-weight:bold;'>"
                f"{html.escape(line[start:end])}</span>"
            )
            pos = end
        if pos < len(line):
            parts.append(
                f"<span style='color:#bdc3c7;'>{html.escape(line[pos:])}</span>"
            )

        return (
            f"<div style='padding:1px 4px;'>"
            f"<span style='color:#7f8c8d;'>{line_num:3d}</span> "
            f"<span style='color:#27ae60;'>✓</span> "
            + "".join(parts)
            + "</div>"
        )


# ---------------------------------------------------------------------------
# Background loader
# ---------------------------------------------------------------------------

class LogLoaderWorker(QThread):
    """Parses a VFS node in a worker thread and emits entries in chunks.

    Signals
    -------
    chunk_ready(int, list[dict])     — (source_id, entries) for each CHUNK_SIZE batch.
    load_finished(int, str, dict)    — (source_id, format_name, metadata) once done.
    error(int, str)                  — (source_id, message) if parsing raises.
    """

    chunk_ready:   Signal = Signal(int, list)
    load_finished: Signal = Signal(int, str, dict)
    error:         Signal = Signal(int, str)

    CHUNK_SIZE = 5_000

    def __init__(
        self,
        node: VFSNode,
        vfs: VFS,
        source_id: int,
        profile: Any = None,          # CustomFormatProfile | None
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._node         = node
        self._vfs          = vfs
        self._source_id    = source_id
        self._profile      = profile
        self._cancel_flag  = False

    def cancel(self) -> None:
        """Request the worker to stop emitting after the current chunk."""
        self._cancel_flag = True

    def run(self) -> None:
        self._cancel_flag = False
        try:
            if self._profile is not None:
                from crush.parsers.multi_log_parser import CustomFormatParser
                parser: Any = CustomFormatParser(self._profile)
            else:
                from crush.parsers.log_parser import LogParser
                parser = LogParser()
            result = parser.parse(self._node, self._vfs)
            entries: list[dict[str, Any]] = result.data  # type: ignore[assignment]
            for i in range(0, len(entries), self.CHUNK_SIZE):
                if self._cancel_flag:
                    return
                self.chunk_ready.emit(self._source_id, entries[i : i + self.CHUNK_SIZE])
            if not self._cancel_flag:
                self.load_finished.emit(
                    self._source_id,
                    result.metadata.get("Log format", "Unknown"),
                    result.metadata,
                )
        except Exception as exc:  # noqa: BLE001
            self.error.emit(self._source_id, str(exc))


# ---------------------------------------------------------------------------
# Virtual table model
# ---------------------------------------------------------------------------

class MultiLogModel(QAbstractTableModel):
    """QAbstractTableModel backed directly by a Python list of entry dicts.

    Filtering is maintained as ``_visible`` — a list of indices into
    ``_entries`` that pass all active filters, ordered by ``_sort_order``.

    During background loading entries are appended via ``append_chunk()``
    using beginInsertRows / endInsertRows (no full reset per chunk).
    After each source finishes loading ``finalize_sort()`` re-sorts everything.

    Multiple sources are tracked in ``_sources``; each source can be toggled
    on/off via ``set_source_visible()``.

    See the module docstring for the full entry dict schema.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[dict[str, Any]] = []
        self._display_tz: tzinfo = timezone.utc

        # Source registry: source_id -> {name, color, visible}
        self._sources: dict[int, dict[str, Any]] = {}
        self._hidden_source_ids: set[int] = set()

        # Sorting — default: ascending by timestamp (applied after load)
        self._sort_col: int = _COL_TS
        self._sort_asc: bool = True
        # During loading _sort_order == natural append order
        self._sort_order: list[int] = []

        # Filter state
        self._allowed_levels: set[str] = set(_LEVELS)
        self._ts_from: datetime | None = None
        self._ts_to:   datetime | None = None
        self._text: str = ""

        self._visible: list[int] = []

    # ------------------------------------------------------------------
    # Source management
    # ------------------------------------------------------------------

    def register_source(self, source_id: int, name: str, color: QColor) -> None:
        self._sources[source_id] = {"name": name, "color": color, "visible": True}

    def set_source_visible(self, source_id: int, visible: bool) -> None:
        src = self._sources.get(source_id)
        if src is None or src["visible"] == visible:
            return
        src["visible"] = visible
        if visible:
            self._hidden_source_ids.discard(source_id)
        else:
            self._hidden_source_ids.add(source_id)
        self._rebuild_visible()

    def source_name(self, source_id: int) -> str:
        src = self._sources.get(source_id)
        return src["name"] if src else ""

    def source_color(self, source_id: int) -> QColor | None:
        src = self._sources.get(source_id)
        return src["color"] if src else None

    # ------------------------------------------------------------------
    # QAbstractTableModel interface
    # ------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._visible)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(_HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        entry = self._entries[self._visible[index.row()]]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == _COL_SRC:
                return entry.get("source", "")
            if col == _COL_TS:
                return _fmt_ts(entry.get("timestamp"), self._display_tz)
            if col == _COL_LVL:
                return entry.get("level", "UNKNOWN")
            if col == _COL_PROC:
                return entry.get("process", "")
            if col == _COL_PID:
                return entry.get("pid", "")
            if col == _COL_MSG:
                return _msg_display(entry.get("message", ""))

        if role == Qt.ItemDataRole.ForegroundRole:
            if col == _COL_LVL:
                return _LEVEL_COLORS.get(entry.get("level", "UNKNOWN"), _LEVEL_COLORS["UNKNOWN"])
            if col == _COL_SRC:
                color = self.source_color(entry.get("source_id", -1))
                if color:
                    return color

        if role == Qt.ItemDataRole.ToolTipRole and col == _COL_MSG:
            msg = entry.get("message", "")
            return msg if "\n" in msg else None

        if role == _ROLE_TS_DT:
            return entry.get("timestamp")
        if role == _ROLE_LEVEL:
            return entry.get("level", "UNKNOWN")
        if role == _ROLE_RAW:
            return entry.get("raw", "")
        if role == _ROLE_MSG_FULL:
            return entry.get("message", "")

        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        asc = order == Qt.SortOrder.AscendingOrder
        self._sort_col = column
        self._sort_asc = asc
        self.beginResetModel()
        self._sort_order = self._build_sort_order(column, asc)
        self._visible = self._apply_filter(self._sort_order)
        self.endResetModel()

    # ------------------------------------------------------------------
    # Incremental loading (called from the main thread via queued signals)
    # ------------------------------------------------------------------

    def append_chunk(self, source_id: int, entries: list[dict[str, Any]]) -> None:
        """Append a chunk of entries from one source.

        Stamps each entry with source_id and source name, then inserts using
        beginInsertRows / endInsertRows so the view only repaints new rows.
        A full sort is applied once per source via finalize_sort().
        """
        if not entries:
            return
        src_name = self.source_name(source_id)
        for e in entries:
            e["source_id"] = source_id
            e["source"]    = src_name

        start_idx = len(self._entries)
        self._entries.extend(entries)
        new_indices = list(range(start_idx, len(self._entries)))
        self._sort_order.extend(new_indices)

        new_visible = self._apply_filter(new_indices)
        if new_visible:
            first_row = len(self._visible)
            last_row = first_row + len(new_visible) - 1
            self.beginInsertRows(QModelIndex(), first_row, last_row)
            self._visible.extend(new_visible)
            self.endInsertRows()

    def finalize_sort(self) -> None:
        """Apply the current sort across all loaded entries.

        Called after each source finishes loading.
        """
        self.beginResetModel()
        self._sort_order = self._build_sort_order(self._sort_col, self._sort_asc)
        self._visible = self._apply_filter(self._sort_order)
        self.endResetModel()

    # ------------------------------------------------------------------
    # Filter setters
    # ------------------------------------------------------------------

    def set_levels(self, levels: set[str]) -> None:
        self._allowed_levels = levels
        self._rebuild_visible()

    def set_time_range(self, from_dt: datetime | None, to_dt: datetime | None) -> None:
        self._ts_from = from_dt
        self._ts_to   = to_dt
        self._rebuild_visible()

    def set_text(self, text: str) -> None:
        self._text = text.lower()
        self._rebuild_visible()

    def set_display_tz(self, tz: tzinfo) -> None:
        self._display_tz = tz
        if self._visible:
            top    = self.index(0, _COL_TS)
            bottom = self.index(len(self._visible) - 1, _COL_TS)
            self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.DisplayRole])

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def total_count(self) -> int:
        return len(self._entries)

    def visible_count(self) -> int:
        return len(self._visible)

    def entry_at(self, proxy_row: int) -> dict[str, Any]:
        return self._entries[self._visible[proxy_row]]

    def timestamp_range(self) -> tuple[datetime | None, datetime | None]:
        timestamps = [e["timestamp"] for e in self._entries if e.get("timestamp") is not None]
        if not timestamps:
            return None, None
        return min(timestamps), max(timestamps)

    def replace_source_entries(
        self,
        source_id: int,
        new_entries: list[dict[str, Any]],
    ) -> None:
        """Replace all entries from one source — used when reloading with a custom format.

        After this call the model contains entries from all *other* sources plus
        ``new_entries`` (stamped with source_id / source name).  A full
        ``finalize_sort()`` is expected to follow once the new worker finishes.
        """
        src_name = self.source_name(source_id)
        # Remove old entries for this source
        self._entries = [e for e in self._entries if e.get("source_id") != source_id]
        # Stamp and append the new ones
        for e in new_entries:
            e["source_id"] = source_id
            e["source"]    = src_name
        self._entries.extend(new_entries)
        # Reset to natural order; finalize_sort() will sort when the worker finishes
        self.beginResetModel()
        self._sort_order = list(range(len(self._entries)))
        self._visible    = self._apply_filter(self._sort_order)
        self.endResetModel()

    def preview_lines_for_source(self, source_id: int, max_lines: int = 20) -> list[str]:
        """Return up to *max_lines* raw log lines for a given source.

        Uses the ``raw`` field from already-loaded entries — no file re-read.
        """
        lines: list[str] = []
        for e in self._entries:
            if e.get("source_id") == source_id:
                raw = e.get("raw", "")
                lines.extend(raw.split("\n"))
                if len(lines) >= max_lines:
                    break
        return lines[:max_lines]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_sort_order(self, column: int, asc: bool) -> list[int]:
        entries = self._entries

        def key(i: int) -> Any:
            e = entries[i]
            if column == _COL_TS:
                dt = e.get("timestamp")
                return (1, float("inf")) if dt is None else (0, dt.timestamp())
            if column == _COL_LVL:
                order = {"ERROR": 0, "WARN": 1, "INFO": 2, "DEBUG": 3, "TRACE": 4, "UNKNOWN": 5}
                return order.get(e.get("level", "UNKNOWN"), 5)
            if column == _COL_SRC:
                return (e.get("source") or "").lower()
            if column == _COL_PROC:
                return (e.get("process") or "").lower()
            if column == _COL_PID:
                return (e.get("pid") or "").lower()
            return (e.get("message") or "").lower()

        indices = list(range(len(entries)))
        indices.sort(key=key, reverse=not asc)
        return indices

    def _apply_filter(self, source: list[int]) -> list[int]:
        allowed        = self._allowed_levels
        hidden_sources = self._hidden_source_ids
        ts_from        = self._ts_from
        ts_to          = self._ts_to
        text           = self._text
        entries        = self._entries
        result: list[int] = []
        for i in source:
            e = entries[i]
            if e.get("level", "UNKNOWN") not in allowed:
                continue
            if hidden_sources and e.get("source_id") in hidden_sources:
                continue
            dt: datetime | None = e.get("timestamp")
            if dt is not None:
                if ts_from and dt < ts_from:
                    continue
                if ts_to and dt > ts_to:
                    continue
            if text:
                extra_values = " ".join((e.get("extra") or {}).values()).lower()
                if text not in (e.get("message") or "").lower() and \
                   text not in (e.get("process") or "").lower() and \
                   text not in (e.get("pid") or "").lower() and \
                   text not in extra_values:
                    continue
            result.append(i)
        return result

    def _rebuild_visible(self) -> None:
        self.beginResetModel()
        self._visible = self._apply_filter(self._sort_order)
        self.endResetModel()


# ---------------------------------------------------------------------------
# Viewer widget
# ---------------------------------------------------------------------------

class MultiLogViewer(QWidget):
    """Multi-Log Studio viewer — Phase 3 (multiple sources, virtual model, async load).

    The first source is loaded immediately from the VFSNode passed to the
    constructor.  Additional sources can be added at any time via add_source()
    or via the "Add Source" button in the source bar.

    Public API (used by main_window for VFS-tree "Add to Multi-Log Studio"):
        add_source(node, vfs) — load an additional log source into this viewer.
    """

    def __init__(
        self,
        node: VFSNode,
        vfs: VFS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._model              = MultiLogModel(self)
        self._display_tz: tzinfo = timezone.utc
        self._workers: dict[int, LogLoaderWorker] = {}
        self._source_chips: dict[int, QPushButton] = {}
        self._source_nodes: dict[int, tuple[VFSNode, VFS]] = {}
        self._next_source_id     = 0
        self._build_ui()
        self.add_source(node, vfs)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_source(self, node: VFSNode, vfs: VFS) -> None:
        """Load an additional log source and merge it into the timeline."""
        sid   = self._next_source_id
        self._next_source_id += 1
        color = _SOURCE_COLORS[sid % len(_SOURCE_COLORS)]

        self._source_nodes[sid] = (node, vfs)
        self._model.register_source(sid, node.name, color)
        self._add_source_chip(sid, node.name, color)

        worker = LogLoaderWorker(node, vfs, sid, parent=self)
        worker.chunk_ready.connect(self._on_chunk_ready)
        worker.load_finished.connect(self._on_load_finished)
        worker.error.connect(self._on_error)
        self._workers[sid] = worker

        self._progress.setVisible(True)
        self._table.setSortingEnabled(False)
        worker.start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_source_bar())

        # Progress bar — shown during loading, hidden when all workers finish
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)          # indeterminate
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        # Time bar — hidden until timestamps are confirmed
        self._time_bar = self._build_time_bar()
        self._time_bar.setVisible(False)
        root.addWidget(self._time_bar)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setSortingEnabled(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_MSG, QHeaderView.ResizeMode.Stretch
        )
        self._table.verticalHeader().setDefaultSectionSize(20)
        self._table.verticalHeader().hide()
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        self._table.selectionModel().selectionChanged.connect(self._on_selection)
        self._table.horizontalHeader().setSortIndicator(_COL_TS, Qt.SortOrder.AscendingOrder)
        splitter.addWidget(self._table)

        self._raw_panel = QPlainTextEdit()
        self._raw_panel.setReadOnly(True)
        self._raw_panel.setPlaceholderText("Select a row to see the original line…")
        self._raw_panel.setMinimumHeight(40)
        self._raw_panel.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        splitter.addWidget(self._raw_panel)

        splitter.setStretchFactor(0, 10)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

        self._model.modelReset.connect(self._update_count)
        self._model.rowsInserted.connect(self._update_count)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(36)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        layout.addWidget(QLabel("Level:"))
        self._level_btns: dict[str, QPushButton] = {}
        for lvl in _LEVELS:
            btn = QPushButton(lvl)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedWidth(62)
            color = _LEVEL_COLORS.get(lvl, QColor("#bdc3c7"))
            btn.setStyleSheet(
                f"QPushButton:checked {{ background-color: {color.name()}; color: white; }}"
            )
            btn.toggled.connect(self._on_level_toggled)
            layout.addWidget(btn)
            self._level_btns[lvl] = btn

        layout.addSpacing(8)

        layout.addWidget(QLabel("Search:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter message / process / extra…")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(200)
        self._search.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search)

        layout.addSpacing(8)
        fmt_btn = QPushButton("Format…")
        fmt_btn.setToolTip("Define or apply a custom log format profile")
        fmt_btn.clicked.connect(self._on_format_clicked)
        layout.addWidget(fmt_btn)

        layout.addStretch()

        self._fmt_label = QLabel("")
        layout.addWidget(self._fmt_label)

        layout.addSpacing(8)

        self._count_label = QLabel("")
        layout.addWidget(self._count_label)

        return bar

    def _build_source_bar(self) -> QWidget:
        """Bar with an 'Add Source' button and one colour chip per loaded source."""
        outer = QWidget()
        outer.setFixedHeight(36)
        outer_layout = QHBoxLayout(outer)
        outer_layout.setContentsMargins(4, 2, 4, 2)
        outer_layout.setSpacing(6)

        add_btn = QPushButton("+ Add Source")
        add_btn.setFixedHeight(26)
        add_btn.clicked.connect(self._on_add_source_clicked)
        outer_layout.addWidget(add_btn)

        # Scrollable area for chips (handles many sources gracefully)
        scroll = QScrollArea()
        scroll.setFrameStyle(0)
        # widgetResizable=False: chip_container keeps its natural width so the
        # scroll area's own size hint doesn't grow when chips are added, which
        # would otherwise force the window to widen.
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedHeight(32)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        chip_container = QWidget()
        self._chip_layout = QHBoxLayout(chip_container)
        self._chip_layout.setContentsMargins(0, 0, 0, 0)
        self._chip_layout.setSpacing(4)
        self._chip_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        # No addStretch() — container width = sum of chip widths; scroll area
        # shows a scrollbar only when chips overflow the available space.

        scroll.setWidget(chip_container)
        outer_layout.addWidget(scroll)

        return outer

    def _add_source_chip(self, source_id: int, name: str, color: QColor) -> None:
        chip = QPushButton(name)
        chip.setCheckable(True)
        chip.setChecked(True)
        chip.setFixedHeight(22)
        chip.setStyleSheet(
            f"QPushButton:checked {{ background-color: {color.name()}; color: white; "
            f"border-radius: 3px; padding: 0 6px; }}"
            f"QPushButton {{ border-radius: 3px; padding: 0 6px; }}"
        )
        chip.toggled.connect(
            lambda checked, sid=source_id: self._model.set_source_visible(sid, checked)
        )
        self._chip_layout.addWidget(chip)
        self._source_chips[source_id] = chip

    def _build_time_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(36)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._time_filter_cb = QCheckBox("Time range:")
        self._time_filter_cb.setChecked(False)
        self._time_filter_cb.toggled.connect(self._on_time_filter_toggled)
        layout.addWidget(self._time_filter_cb)

        self._dt_from = QDateTimeEdit()
        self._dt_from.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self._dt_from.setCalendarPopup(True)
        self._dt_from.setEnabled(False)
        self._dt_from.setTimeSpec(Qt.TimeSpec.UTC)
        layout.addWidget(self._dt_from)

        layout.addWidget(QLabel("–"))

        self._dt_to = QDateTimeEdit()
        self._dt_to.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self._dt_to.setCalendarPopup(True)
        self._dt_to.setEnabled(False)
        self._dt_to.setTimeSpec(Qt.TimeSpec.UTC)
        layout.addWidget(self._dt_to)

        self._time_reset_btn = QPushButton("Reset")
        self._time_reset_btn.setEnabled(False)
        self._time_reset_btn.clicked.connect(self._reset_time_filter)
        layout.addWidget(self._time_reset_btn)

        layout.addSpacing(16)

        layout.addWidget(QLabel("Display TZ:"))
        self._tz_combo = QComboBox()
        self._tz_combo.addItem("UTC", timezone.utc)
        self._tz_combo.addItem("Local", None)
        self._tz_combo.currentIndexChanged.connect(self._on_tz_changed)
        layout.addWidget(self._tz_combo)

        self._dt_from.dateTimeChanged.connect(self._apply_time_filter)
        self._dt_to.dateTimeChanged.connect(self._apply_time_filter)

        layout.addStretch()
        return bar

    # ------------------------------------------------------------------
    # Worker signal handlers
    # ------------------------------------------------------------------

    def _on_chunk_ready(self, source_id: int, entries: list[dict[str, Any]]) -> None:
        self._model.append_chunk(source_id, entries)

    def _on_load_finished(self, source_id: int, fmt: str, _metadata: dict[str, Any]) -> None:
        self._model.finalize_sort()
        self._update_count()

        # Resize fixed columns (idempotent; cheap after finalize_sort)
        for col in (_COL_SRC, _COL_TS, _COL_LVL, _COL_PROC, _COL_PID):
            self._table.resizeColumnToContents(col)

        # Append source info to the format label
        src_name = self._model.source_name(source_id)
        new_entry = f"{src_name}: {fmt}"
        existing = self._fmt_label.text()
        self._fmt_label.setText(new_entry if not existing else f"{existing}  |  {new_entry}")

        # Enable sorting + hide progress once every worker has finished
        if all(not w.isRunning() for w in self._workers.values()):
            self._table.setSortingEnabled(True)
            self._progress.setVisible(False)

        # Show / expand time bar to cover the full merged range
        ts_min, ts_max = self._model.timestamp_range()
        if ts_min is not None and ts_max is not None:
            self._dt_from.setDateTime(
                QDateTime.fromSecsSinceEpoch(int(ts_min.timestamp()), Qt.TimeSpec.UTC)
            )
            self._dt_to.setDateTime(
                QDateTime.fromSecsSinceEpoch(int(ts_max.timestamp()), Qt.TimeSpec.UTC)
            )
            self._time_bar.setVisible(True)

    def _on_error(self, source_id: int, message: str) -> None:
        src_name = self._model.source_name(source_id) or "?"
        self._fmt_label.setText(f"Error ({src_name}): {message}")
        if all(not w.isRunning() for w in self._workers.values()):
            self._progress.setVisible(False)

    # ------------------------------------------------------------------
    # Slot handlers — Format button (Phase 4)
    # ------------------------------------------------------------------

    def _on_format_clicked(self) -> None:
        if not self._source_nodes:
            return
        # Build source list for the dialog's "Apply to source" combo
        sources = [
            (sid, self._model.source_name(sid))
            for sid in sorted(self._source_nodes)
        ]
        # Collect preview lines from the first source using already-loaded entries
        first_sid = sources[0][0]
        preview_lines = self._model.preview_lines_for_source(
            first_sid, DefineFormatDialog.PREVIEW_LINES
        )
        dlg = DefineFormatDialog(preview_lines, sources, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            profile = dlg.result_profile()
            if profile is not None:
                self.reload_source_with_profile(dlg.result_source_id(), profile)

    def reload_source_with_profile(self, source_id: int, profile: Any) -> None:
        """Re-parse an existing source using a custom format profile.

        Cancels the existing worker for that source (if still running),
        clears its entries from the model, then starts a fresh worker
        backed by ``profile``.
        """
        if source_id not in self._source_nodes:
            return
        node, vfs = self._source_nodes[source_id]

        # Stop the old worker if it is still loading
        old_worker = self._workers.get(source_id)
        if old_worker is not None and old_worker.isRunning():
            old_worker.cancel()
            old_worker.wait()   # brief block — parse is typically fast

        # Clear existing entries for this source
        self._model.replace_source_entries(source_id, [])

        # Launch a fresh worker with the custom profile
        worker = LogLoaderWorker(node, vfs, source_id, profile=profile, parent=self)
        worker.chunk_ready.connect(self._on_chunk_ready)
        worker.load_finished.connect(self._on_load_finished)
        worker.error.connect(self._on_error)
        self._workers[source_id] = worker

        self._progress.setVisible(True)
        self._table.setSortingEnabled(False)
        worker.start()

    # ------------------------------------------------------------------
    # Slot handlers — Add Source button
    # ------------------------------------------------------------------

    def _on_add_source_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Add Log Source",
            "",
            "Log files (*.log *.txt *.json *.jsonl *.csv);;All files (*)",
        )
        if not path:
            return
        from crush.core.vfs import FileVFS
        vfs  = FileVFS(path)
        self.add_source(vfs.root(), vfs)

    # ------------------------------------------------------------------
    # Slot handlers — filters
    # ------------------------------------------------------------------

    def _on_level_toggled(self) -> None:
        allowed = {lvl for lvl, btn in self._level_btns.items() if btn.isChecked()}
        self._model.set_levels(allowed)

    def _on_search_changed(self, text: str) -> None:
        self._model.set_text(text)

    def _on_time_filter_toggled(self, checked: bool) -> None:
        self._dt_from.setEnabled(checked)
        self._dt_to.setEnabled(checked)
        self._time_reset_btn.setEnabled(checked)
        if checked:
            self._apply_time_filter()
        else:
            self._model.set_time_range(None, None)

    def _apply_time_filter(self) -> None:
        if not self._time_filter_cb.isChecked():
            return
        from_dt = datetime.fromtimestamp(
            self._dt_from.dateTime().toSecsSinceEpoch(), tz=timezone.utc
        )
        to_dt = datetime.fromtimestamp(
            self._dt_to.dateTime().toSecsSinceEpoch(), tz=timezone.utc
        )
        self._model.set_time_range(from_dt, to_dt)

    def _reset_time_filter(self) -> None:
        ts_min, ts_max = self._model.timestamp_range()
        spec = Qt.TimeSpec.UTC if self._display_tz is timezone.utc else Qt.TimeSpec.LocalTime
        if ts_min:
            self._dt_from.setDateTime(
                QDateTime.fromSecsSinceEpoch(int(ts_min.timestamp()), spec)
            )
        if ts_max:
            self._dt_to.setDateTime(
                QDateTime.fromSecsSinceEpoch(int(ts_max.timestamp()), spec)
            )
        self._model.set_time_range(None, None)

    def _on_tz_changed(self, index: int) -> None:
        tz_data = self._tz_combo.itemData(index)
        self._display_tz = tz_data if tz_data is not None else datetime.now().astimezone().tzinfo
        self._model.set_display_tz(self._display_tz)
        spec = Qt.TimeSpec.UTC if tz_data is timezone.utc else Qt.TimeSpec.LocalTime
        if self._time_bar.isVisible():
            for widget in (self._dt_from, self._dt_to):
                widget.setTimeSpec(spec)
            self._reset_time_filter()

    # ------------------------------------------------------------------
    # Slot handlers — table interaction
    # ------------------------------------------------------------------

    def _on_selection(self) -> None:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            self._raw_panel.clear()
            return
        entry = self._model.entry_at(indexes[0].row())
        parts = [entry.get("raw", "")]
        extra: dict[str, str] = entry.get("extra") or {}
        if extra:
            parts.append("\n--- Extra Fields ---")
            parts.extend(f"{k}: {v}" for k, v in extra.items())
        self._raw_panel.setPlainText("\n".join(parts))

    def _on_context_menu(self, pos: object) -> None:
        index = self._table.indexAt(pos)
        if not index.isValid():
            return
        menu = QMenu(self)
        copy_msg  = menu.addAction("Copy message")
        copy_raw  = menu.addAction("Copy raw line")
        copy_rows = menu.addAction("Copy selection (TSV)")
        action = menu.exec(self._table.viewport().mapToGlobal(pos))
        row = index.row()
        entry = self._model.entry_at(row)
        if action == copy_msg:
            QApplication.clipboard().setText(_msg_display(entry.get("message", "")))
        elif action == copy_raw:
            QApplication.clipboard().setText(entry.get("raw", ""))
        elif action == copy_rows:
            rows = sorted({i.row() for i in self._table.selectedIndexes()})
            lines: list[str] = []
            for r in rows:
                e = self._model.entry_at(r)
                lines.append("\t".join([
                    e.get("source", ""),
                    _fmt_ts(e.get("timestamp"), self._display_tz),
                    e.get("level", ""),
                    e.get("process", ""),
                    e.get("pid", ""),
                    _msg_display(e.get("message", "")),
                ]))
            QApplication.clipboard().setText("\n".join(lines))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_count(self) -> None:
        visible = self._model.visible_count()
        total   = self._model.total_count()
        if total == 0:
            self._count_label.setText("")
        elif visible == total:
            word = "entry" if total == 1 else "entries"
            self._count_label.setText(f"{total:,} {word}")
        else:
            self._count_label.setText(f"{visible:,} of {total:,} entries")
