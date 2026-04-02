# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Log viewer — displays structured log entries with level and time filters."""
from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from typing import Any

from PySide6.QtCore import (
    QDateTime,
    QSortFilterProxyModel,
    Qt,
    QModelIndex,
)
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LEVELS = ["ERROR", "WARN", "INFO", "DEBUG", "TRACE", "UNKNOWN"]

_LEVEL_COLORS: dict[str, QColor] = {
    "ERROR": QColor("#c0392b"),
    "WARN":  QColor("#e67e22"),
    "INFO":  QColor("#2980b9"),
    "DEBUG": QColor("#7f8c8d"),
    "TRACE": QColor("#95a5a6"),
    "UNKNOWN": QColor("#bdc3c7"),
}

# Column indices
_COL_TS   = 0
_COL_LVL  = 1
_COL_PROC = 2
_COL_MSG  = 3

_ROLE_TS_DT   = Qt.ItemDataRole.UserRole + 1   # datetime | None
_ROLE_LEVEL   = Qt.ItemDataRole.UserRole + 2   # str
_ROLE_RAW     = Qt.ItemDataRole.UserRole + 3   # str (original line)
_ROLE_SORT    = Qt.ItemDataRole.UserRole + 4   # sortable value


def _fmt_ts(dt: datetime | None, tz: tzinfo = timezone.utc) -> str:
    if dt is None:
        return "—"
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Proxy model — filters by level set + time range + text search
# ---------------------------------------------------------------------------

class _LogFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._allowed_levels: set[str] = set(_LEVELS)
        self._ts_from: datetime | None = None
        self._ts_to:   datetime | None = None
        self._text: str = ""
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_levels(self, levels: set[str]) -> None:
        self._allowed_levels = levels
        self.invalidateFilter()

    def set_time_range(self, from_dt: datetime | None, to_dt: datetime | None) -> None:
        self._ts_from = from_dt
        self._ts_to   = to_dt
        self.invalidateFilter()

    def set_text(self, text: str) -> None:
        self._text = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        ts_idx  = model.index(source_row, _COL_TS,  source_parent)
        lvl_idx = model.index(source_row, _COL_LVL, source_parent)
        msg_idx = model.index(source_row, _COL_MSG,  source_parent)
        prc_idx = model.index(source_row, _COL_PROC, source_parent)

        # -- level filter --
        level = model.data(lvl_idx, _ROLE_LEVEL) or "UNKNOWN"
        if level not in self._allowed_levels:
            return False

        # -- time range filter (only if entry has a timestamp) --
        dt: datetime | None = model.data(ts_idx, _ROLE_TS_DT)
        if dt is not None:
            if self._ts_from and dt < self._ts_from:
                return False
            if self._ts_to   and dt > self._ts_to:
                return False
        # entries without timestamp always pass the time filter

        # -- text search --
        if self._text:
            msg  = (model.data(msg_idx) or "").lower()
            proc = (model.data(prc_idx) or "").lower()
            if self._text not in msg and self._text not in proc:
                return False

        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        # Sort timestamp column by datetime object
        if left.column() == _COL_TS:
            l_dt: datetime | None = self.sourceModel().data(left,  _ROLE_TS_DT)
            r_dt: datetime | None = self.sourceModel().data(right, _ROLE_TS_DT)
            if l_dt is not None and r_dt is not None:
                return l_dt < r_dt
            if l_dt is None:
                return True
            return False
        return super().lessThan(left, right)


# ---------------------------------------------------------------------------
# Main viewer widget
# ---------------------------------------------------------------------------

class LogViewer(QWidget):
    """Viewer for structured log data produced by LogParser.

    data: list[dict] where each dict has keys:
        timestamp : datetime | None
        level     : str
        process   : str
        message   : str
        raw       : str
    """

    def __init__(self, data: list[dict[str, Any]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data = data
        self._has_timestamps = any(e["timestamp"] is not None for e in data)
        self._display_tz: tzinfo = timezone.utc  # default: UTC
        self._build_ui()
        self._populate()
        self._update_count()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Proxy must exist before _build_toolbar() connects signals to it
        self._proxy = _LogFilterProxy(self)

        root.addWidget(self._build_toolbar())
        if self._has_timestamps:
            root.addWidget(self._build_time_bar())

        splitter = QSplitter(Qt.Orientation.Vertical)

        # --- table ---
        self._source_model = QStandardItemModel()
        self._source_model.setHorizontalHeaderLabels(
            ["Timestamp", "Level", "Process / Tag", "Message"]
        )

        self._proxy.setSourceModel(self._source_model)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSortingEnabled(True)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setDefaultSectionSize(20)
        self._table.verticalHeader().hide()
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        self._table.selectionModel().selectionChanged.connect(self._on_selection)
        # default sort: timestamp ascending
        self._table.sortByColumn(_COL_TS, Qt.SortOrder.AscendingOrder)
        splitter.addWidget(self._table)

        # --- raw line panel ---
        self._raw_panel = QPlainTextEdit()
        self._raw_panel.setReadOnly(True)
        self._raw_panel.setPlaceholderText("Select a row to see the original line…")
        self._raw_panel.setMinimumHeight(40)
        self._raw_panel.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        splitter.addWidget(self._raw_panel)

        splitter.setStretchFactor(0, 10)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(36)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # Level toggle buttons
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

        # Text search
        layout.addWidget(QLabel("Search:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter message / process…")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(200)
        self._search.textChanged.connect(self._proxy.set_text)
        layout.addWidget(self._search)

        layout.addStretch()

        self._count_label = QLabel("")
        layout.addWidget(self._count_label)

        return bar

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

        ts_min, ts_max = self._timestamp_range()

        self._dt_from = QDateTimeEdit()
        self._dt_from.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self._dt_from.setCalendarPopup(True)
        self._dt_from.setEnabled(False)
        self._dt_from.setTimeSpec(Qt.TimeSpec.UTC)
        if ts_min:
            self._dt_from.setDateTime(QDateTime.fromSecsSinceEpoch(int(ts_min.timestamp()), Qt.TimeSpec.UTC))
        layout.addWidget(self._dt_from)

        layout.addWidget(QLabel("–"))

        self._dt_to = QDateTimeEdit()
        self._dt_to.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self._dt_to.setCalendarPopup(True)
        self._dt_to.setEnabled(False)
        self._dt_to.setTimeSpec(Qt.TimeSpec.UTC)
        if ts_max:
            self._dt_to.setDateTime(QDateTime.fromSecsSinceEpoch(int(ts_max.timestamp()), Qt.TimeSpec.UTC))
        layout.addWidget(self._dt_to)

        reset_btn = QPushButton("Reset")
        reset_btn.setEnabled(False)
        reset_btn.clicked.connect(self._reset_time_filter)
        self._time_reset_btn = reset_btn
        layout.addWidget(reset_btn)

        layout.addSpacing(16)

        # Timezone selector
        layout.addWidget(QLabel("Display TZ:"))
        self._tz_combo = QComboBox()
        self._tz_combo.addItem("UTC", timezone.utc)
        self._tz_combo.addItem("Local", None)  # None → resolve at runtime
        self._tz_combo.currentIndexChanged.connect(self._on_tz_changed)
        layout.addWidget(self._tz_combo)

        self._dt_from.dateTimeChanged.connect(self._apply_time_filter)
        self._dt_to.dateTimeChanged.connect(self._apply_time_filter)

        layout.addStretch()
        return bar

    # ------------------------------------------------------------------
    # Populate model
    # ------------------------------------------------------------------

    def _populate(self) -> None:
        self._source_model.setRowCount(0)
        for entry in self._data:
            dt: datetime | None = entry.get("timestamp")
            level  = entry.get("level", "UNKNOWN")
            proc   = entry.get("process", "")
            msg    = entry.get("message", "")
            raw    = entry.get("raw", "")

            color = _LEVEL_COLORS.get(level, _LEVEL_COLORS["UNKNOWN"])

            ts_item = QStandardItem(_fmt_ts(dt, self._display_tz))
            ts_item.setEditable(False)
            ts_item.setData(dt,  _ROLE_TS_DT)
            # sortable: use timestamp as float, None → -inf
            ts_item.setData(dt.timestamp() if dt else float("-inf"), _ROLE_SORT)

            lvl_item = QStandardItem(level)
            lvl_item.setEditable(False)
            lvl_item.setData(level, _ROLE_LEVEL)
            lvl_item.setData(raw,   _ROLE_RAW)
            lvl_item.setForeground(color)

            proc_item = QStandardItem(proc)
            proc_item.setEditable(False)

            # Show only first line in the table; indicate continuation with line count
            if "\n" in msg:
                lines = msg.split("\n")
                msg_display = f"{lines[0]}  [{len(lines) - 1} more line{'s' if len(lines) > 2 else ''}]"
            else:
                msg_display = msg
            msg_item = QStandardItem(msg_display)
            msg_item.setToolTip(msg if "\n" in msg else "")
            msg_item.setData(msg, _ROLE_RAW + 1)  # store full message
            msg_item.setEditable(False)

            self._source_model.appendRow([ts_item, lvl_item, proc_item, msg_item])

        self._table.resizeColumnToContents(_COL_TS)
        self._table.resizeColumnToContents(_COL_LVL)
        self._table.resizeColumnToContents(_COL_PROC)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _timestamp_range(self) -> tuple[datetime | None, datetime | None]:
        timestamps = [e["timestamp"] for e in self._data if e.get("timestamp") is not None]
        if not timestamps:
            return None, None
        return min(timestamps), max(timestamps)

    def _update_count(self) -> None:
        visible = self._proxy.rowCount()
        total   = self._source_model.rowCount()
        if visible == total:
            word = "entry" if total == 1 else "entries"
            self._count_label.setText(f"{total:,} {word}")
        else:
            self._count_label.setText(f"{visible:,} of {total:,} entries")

    # ------------------------------------------------------------------
    # Slot handlers
    # ------------------------------------------------------------------

    def _on_level_toggled(self) -> None:
        allowed = {lvl for lvl, btn in self._level_btns.items() if btn.isChecked()}
        self._proxy.set_levels(allowed)
        self._update_count()

    def _on_time_filter_toggled(self, checked: bool) -> None:
        self._dt_from.setEnabled(checked)
        self._dt_to.setEnabled(checked)
        self._time_reset_btn.setEnabled(checked)
        if checked:
            self._apply_time_filter()
        else:
            self._proxy.set_time_range(None, None)
            self._update_count()

    def _apply_time_filter(self) -> None:
        if not self._time_filter_cb.isChecked():
            return
        from_dt = datetime.fromtimestamp(
            self._dt_from.dateTime().toSecsSinceEpoch(), tz=timezone.utc
        )
        to_dt = datetime.fromtimestamp(
            self._dt_to.dateTime().toSecsSinceEpoch(), tz=timezone.utc
        )
        self._proxy.set_time_range(from_dt, to_dt)
        self._update_count()

    def _reset_time_filter(self) -> None:
        ts_min, ts_max = self._timestamp_range()
        spec = Qt.TimeSpec.UTC if self._display_tz is timezone.utc else Qt.TimeSpec.LocalTime
        if ts_min:
            self._dt_from.setDateTime(QDateTime.fromSecsSinceEpoch(int(ts_min.timestamp()), spec))
        if ts_max:
            self._dt_to.setDateTime(QDateTime.fromSecsSinceEpoch(int(ts_max.timestamp()), spec))
        self._proxy.set_time_range(None, None)
        self._update_count()

    def _on_tz_changed(self, index: int) -> None:
        tz_data = self._tz_combo.itemData(index)
        self._display_tz = tz_data if tz_data is not None else datetime.now().astimezone().tzinfo
        # Switch QDateTimeEdit time spec so the picker shows the right zone
        spec = Qt.TimeSpec.UTC if tz_data is timezone.utc else Qt.TimeSpec.LocalTime
        for widget in (self._dt_from, self._dt_to):
            widget.setTimeSpec(spec)
        # Update timestamp column display text
        for row in range(self._source_model.rowCount()):
            item = self._source_model.item(row, _COL_TS)
            if item:
                dt: datetime | None = item.data(_ROLE_TS_DT)
                item.setText(_fmt_ts(dt, self._display_tz))
        self._reset_time_filter()

    def _on_selection(self) -> None:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            self._raw_panel.clear()
            return
        src_idx = self._proxy.mapToSource(indexes[0])
        raw = self._source_model.item(src_idx.row(), _COL_LVL)
        if raw:
            self._raw_panel.setPlainText(raw.data(_ROLE_RAW) or "")

    def _on_context_menu(self, pos: object) -> None:
        index = self._table.indexAt(pos)
        if not index.isValid():
            return
        menu = QMenu(self)
        copy_msg  = menu.addAction("Copy message")
        copy_raw  = menu.addAction("Copy raw line")
        copy_rows = menu.addAction("Copy selection (TSV)")
        action = menu.exec(self._table.viewport().mapToGlobal(pos))
        src_idx = self._proxy.mapToSource(index)
        row = src_idx.row()
        if action == copy_msg:
            msg = self._source_model.item(row, _COL_MSG)
            if msg:
                QApplication.clipboard().setText(msg.text())
        elif action == copy_raw:
            lvl_item = self._source_model.item(row, _COL_LVL)
            if lvl_item:
                QApplication.clipboard().setText(lvl_item.data(_ROLE_RAW) or "")
        elif action == copy_rows:
            rows = sorted({
                self._proxy.mapToSource(i).row()
                for i in self._table.selectedIndexes()
            })
            lines: list[str] = []
            for r in rows:
                parts = [
                    self._source_model.item(r, c).text()
                    for c in range(self._source_model.columnCount())
                    if self._source_model.item(r, c)
                ]
                lines.append("\t".join(parts))
            QApplication.clipboard().setText("\n".join(lines))
