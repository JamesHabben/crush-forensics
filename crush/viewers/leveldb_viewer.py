# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""LevelDB viewer — overview, files, records (all + deleted)."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QSortFilterProxyModel
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QLabel,
    QMenu,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from crush.viewers.hex_viewer import HexViewer
from crush.viewers.table_viewer import BlobInspector
from crush.viewers.tree_viewer import TreeViewer

# Raw bytes stored alongside display text via custom item data roles
_KEY_BYTES_ROLE = Qt.ItemDataRole.UserRole + 1
_VAL_BYTES_ROLE = Qt.ItemDataRole.UserRole + 2

_STATE_COLORS: dict[str, QColor] = {
    "Deleted": QColor("#cc3333"),
    "Unknown": QColor("#888888"),
}

_COLUMNS = [
    "Seq",
    "State",
    "File",
    "User Key (text)",
    "User Key (hex)",
    "Value (text)",
    "Value (hex)",
    "Compressed",
]

# Number of bytes shown as hex preview in the table columns
_HEX_PREVIEW_BYTES = 16


def _hex_preview(raw: bytes) -> str:
    if not raw:
        return ""
    preview = raw[:_HEX_PREVIEW_BYTES].hex(" ")
    if len(raw) > _HEX_PREVIEW_BYTES:
        preview += f"  ({len(raw)} B)"
    return preview


def _text_preview(text: str | None, raw: bytes) -> str:
    if text is not None:
        if len(text) > 120:
            return text[:120] + "…"
        return text
    return f"<binary {len(raw)} B>"


class _StateFilterProxy(QSortFilterProxyModel):
    """Filters rows by the State column (index 1). Empty filter = show all."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state: str | None = None

    def set_state(self, state: str | None) -> None:
        self._state = state
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: Any) -> bool:
        if self._state is None:
            return True
        idx = self.sourceModel().index(source_row, 1, source_parent)
        return self.sourceModel().data(idx) == self._state


class LevelDbRecordsWidget(QWidget):
    """Reusable splitter: records table (top) + HexViewer of selected row (bottom).

    initial_filter: "Live" | "Deleted" | "Unknown" | None (show all)
    """

    def __init__(
        self,
        records: list[dict[str, Any]],
        initial_filter: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._records = records
        self._initial_filter = initial_filter
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- filter toolbar ---
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.addWidget(QLabel("  Show: "))

        self._filter_buttons: dict[str | None, QPushButton] = {}
        for label, state in [("All", None), ("Live", "Live"), ("Deleted", "Deleted"), ("Unknown", "Unknown")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.clicked.connect(lambda checked, s=state: self._apply_filter(s))
            toolbar.addWidget(btn)
            self._filter_buttons[state] = btn

        layout.addWidget(toolbar)

        # --- splitter: table + hex ---
        splitter = QSplitter(Qt.Orientation.Vertical)

        self._model = QStandardItemModel(0, len(_COLUMNS))
        self._model.setHorizontalHeaderLabels(_COLUMNS)
        self._populate_model()

        self._proxy = _StateFilterProxy()
        self._proxy.setSourceModel(self._model)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.resizeColumnsToContents()
        self._table.selectionModel().currentRowChanged.connect(self._on_row_changed)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        splitter.addWidget(self._table)

        self._hex = HexViewer(b"", splitter)
        splitter.addWidget(self._hex)
        splitter.setSizes([400, 200])

        layout.addWidget(splitter)

        # activate initial filter
        self._apply_filter(self._initial_filter)

    def _populate_model(self) -> None:
        for rec in self._records:
            state = rec["state"]
            color = _STATE_COLORS.get(state)

            uk_bytes: bytes = rec.get("user_key_bytes") or b""
            val_bytes: bytes = rec.get("value_bytes") or b""

            cells = [
                str(rec.get("seq", "")),
                state,
                rec.get("file", ""),
                _text_preview(rec.get("user_key_text"), uk_bytes),
                _hex_preview(uk_bytes),
                _text_preview(rec.get("value_text"), val_bytes),
                _hex_preview(val_bytes),
                "yes" if rec.get("compressed") else "no",
            ]

            items = []
            for i, text in enumerate(cells):
                item = QStandardItem(text)
                item.setEditable(False)
                if color:
                    item.setForeground(color)
                items.append(item)

            # Store raw bytes for hex pane and inspector
            items[0].setData(uk_bytes, _KEY_BYTES_ROLE)
            items[0].setData(val_bytes, _VAL_BYTES_ROLE)

            self._model.appendRow(items)

    def _apply_filter(self, state: str | None) -> None:
        self._proxy.set_state(state)
        for s, btn in self._filter_buttons.items():
            btn.setChecked(s == state)

        # update label to show visible / total
        total = self._model.rowCount()
        for s, btn in self._filter_buttons.items():
            if s is None:
                btn.setText(f"All ({total})")
            else:
                count = sum(1 for r in self._records if r["state"] == s)
                btn.setText(f"{s} ({count})")

    def _source_row(self, proxy_index) -> int:
        return self._proxy.mapToSource(proxy_index).row()

    def _on_row_changed(self, current, _previous) -> None:
        row = self._source_row(current)
        if 0 <= row < self._model.rowCount():
            item = self._model.item(row, 0)
            uk = item.data(_KEY_BYTES_ROLE) or b""
            val = item.data(_VAL_BYTES_ROLE) or b""
            self._hex.set_data(uk + b"\n--- value ---\n" + val)

    def _on_context_menu(self, pos) -> None:
        proxy_index = self._table.indexAt(pos)
        if not proxy_index.isValid():
            return
        row = self._source_row(proxy_index)
        if row < 0 or row >= self._model.rowCount():
            return
        item = self._model.item(row, 0)
        uk: bytes = item.data(_KEY_BYTES_ROLE) or b""
        val: bytes = item.data(_VAL_BYTES_ROLE) or b""

        menu = QMenu(self)
        inspect_key = menu.addAction(f"Inspect Key… ({len(uk)} B)")
        inspect_val = menu.addAction(f"Inspect Value… ({len(val)} B)")
        action = menu.exec(self._table.viewport().mapToGlobal(pos))
        if action == inspect_key and uk:
            BlobInspector(uk, self).exec()
        elif action == inspect_val and val:
            BlobInspector(val, self).exec()


class LevelDbViewer(QWidget):
    """LevelDB viewer with tabs: Overview | Files | Records | Deleted Records."""

    def __init__(self, data: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data = data
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()

        records: list[dict[str, Any]] = self._data.get("records", [])
        files: list[dict[str, Any]] = self._data.get("files", [])
        manifest: dict[str, Any] = self._data.get("manifest", {})

        # --- Overview ---
        if manifest:
            tabs.addTab(TreeViewer({"MANIFEST": manifest}, tabs), "Overview")
        else:
            lbl = QLabel("No MANIFEST file found.")
            lbl.setWordWrap(True)
            tabs.addTab(lbl, "Overview")

        # --- Files ---
        if files:
            tabs.addTab(self._build_files_tab(files, tabs), "Files")

        # --- Records (all, with filter toolbar) ---
        if records:
            total = len(records)
            tabs.addTab(
                LevelDbRecordsWidget(records, initial_filter=None, parent=tabs),
                f"Records ({total:,})",
            )

        layout.addWidget(tabs)

    def _build_files_tab(self, files: list[dict[str, Any]], parent: QWidget) -> QWidget:
        columns = ["File", "Type", "Level", "Total", "Live", "Deleted", "Unknown"]
        model = QStandardItemModel(0, len(columns))
        model.setHorizontalHeaderLabels(columns)

        for f in files:
            level = f.get("level", -1)
            level_str = str(level) if level >= 0 else "—"
            row = [
                QStandardItem(f.get("name", "")),
                QStandardItem(f.get("type", "")),
                QStandardItem(level_str),
                QStandardItem(str(f.get("total", 0))),
                QStandardItem(str(f.get("live", 0))),
                QStandardItem(str(f.get("deleted", 0))),
                QStandardItem(str(f.get("unknown", 0))),
            ]
            for item in row:
                item.setEditable(False)
            # Color files that contain deleted records
            if f.get("deleted", 0) > 0:
                for item in row:
                    item.setForeground(_STATE_COLORS["Deleted"])
            model.appendRow(row)

        table = QTableView()
        table.setModel(model)
        table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        table.setSortingEnabled(True)
        table.horizontalHeader().setStretchLastSection(True)
        table.resizeColumnsToContents()

        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(table)
        return widget
