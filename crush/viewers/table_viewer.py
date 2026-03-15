# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Table viewer — displays SQLite tables as a sortable, searchable grid."""
from __future__ import annotations

from typing import Any

import csv
import sqlite3
from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtGui import QKeySequence, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QPlainTextEdit,
    QTableView,
    QVBoxLayout,
    QWidget,
)


class TableViewer(QWidget):
    """Viewer for SQLite databases.

    data shape:
        {
          "table_name": {
              "columns": ["col1", "col2", ...],
              "rows":    [[val, val, ...], ...]
          },
          ...
        }
    """

    def __init__(self, data: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data = data
        self._db_path = Path(data.get("__db_path", "")) if isinstance(data, dict) else None
        self._db_conn: sqlite3.Connection | None = None
        self._build_ui()
        if data:
            table_names = [k for k in data.keys() if not k.startswith("__")]
            if table_names:
                self._load_table(table_names[0])

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar row: table selector + row count + search
        toolbar = QWidget()
        toolbar.setFixedHeight(36)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)
        toolbar_layout.setSpacing(8)

        toolbar_layout.addWidget(QLabel("Table:"))

        self._table_combo = QComboBox()
        self._table_combo.addItems([k for k in self._data.keys() if not k.startswith("__")])
        self._table_combo.currentTextChanged.connect(self._load_table)
        toolbar_layout.addWidget(self._table_combo)

        self._row_count_label = QLabel("")
        toolbar_layout.addWidget(self._row_count_label)

        toolbar_layout.addStretch()

        search_label = QLabel("Search:")
        toolbar_layout.addWidget(search_label)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter rows…")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedWidth(200)
        self._search.textChanged.connect(self._apply_filter)
        toolbar_layout.addWidget(self._search)

        layout.addWidget(toolbar)

        # SQL row
        sql_bar = QWidget()
        sql_layout = QHBoxLayout(sql_bar)
        sql_layout.setContentsMargins(8, 4, 8, 4)
        sql_layout.setSpacing(8)
        sql_layout.addWidget(QLabel("SQL:"))
        self._sql_input = QPlainTextEdit()
        self._sql_input.setPlaceholderText("SELECT * FROM table LIMIT 100;")
        self._sql_input.setFixedHeight(50)
        sql_layout.addWidget(self._sql_input, stretch=1)
        self._run_sql_btn = QPushButton("Run")
        self._run_sql_btn.clicked.connect(self._run_sql)
        sql_layout.addWidget(self._run_sql_btn)
        self._export_btn = QPushButton("Export CSV…")
        self._export_btn.clicked.connect(self._export_csv)
        sql_layout.addWidget(self._export_btn)
        self._sql_status = QLabel("")
        sql_layout.addWidget(self._sql_status)
        layout.addWidget(sql_bar)

        # Table view
        self._source_model = QStandardItemModel()
        self._proxy_model = _NumericSortProxy()
        self._proxy_model.setSourceModel(self._source_model)
        self._proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy_model.setFilterKeyColumn(-1)  # Search all columns

        self._table_view = QTableView()
        self._table_view.setModel(self._proxy_model)
        self._table_view.setSortingEnabled(True)
        self._table_view.setAlternatingRowColors(True)
        self._table_view.setSelectionBehavior(
            QTableView.SelectionBehavior.SelectRows
        )
        self._table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table_view.customContextMenuRequested.connect(self._on_context_menu)
        self._table_view.horizontalHeader().setStretchLastSection(True)
        self._table_view.verticalHeader().setDefaultSectionSize(22)
        layout.addWidget(self._table_view)

    def _load_table(self, table_name: str) -> None:
        """Populate the model with the selected table's data."""
        table = self._data.get(table_name)
        if table is None:
            return

        columns: list[str] = table["columns"]
        rows: list[list[Any]] = table["rows"]

        self._source_model.clear()
        self._source_model.setHorizontalHeaderLabels(["Row"] + columns)

        for row_index, row_data in enumerate(rows, start=1):
            items = []
            row_item = QStandardItem(str(row_index))
            row_item.setEditable(False)
            row_item.setData(row_index, Qt.ItemDataRole.UserRole)
            items.append(row_item)
            for val in row_data:
                if val is None:
                    cell = QStandardItem("")
                    cell.setForeground(Qt.GlobalColor.gray)
                elif isinstance(val, bytes):
                    cell = QStandardItem(f"<BLOB {len(val):,} B>")
                    cell.setForeground(Qt.GlobalColor.blue)
                    cell.setData(val, Qt.ItemDataRole.UserRole)
                else:
                    cell = QStandardItem(str(val))
                if isinstance(val, (int, float)):
                    cell.setData(val, Qt.ItemDataRole.UserRole)
                cell.setEditable(False)
                items.append(cell)
            self._source_model.appendRow(items)

        self._table_view.resizeColumnsToContents()
        row_word = "row" if len(rows) == 1 else "rows"
        self._row_count_label.setText(f"({len(rows):,} {row_word})")

    def _apply_filter(self, text: str) -> None:
        self._proxy_model.setFilterFixedString(text)
        visible = self._proxy_model.rowCount()
        total = self._source_model.rowCount()
        if text:
            self._row_count_label.setText(f"({visible:,} of {total:,} rows)")
        else:
            word = "row" if total == 1 else "rows"
            self._row_count_label.setText(f"({total:,} {word})")

    def _ensure_db(self) -> sqlite3.Connection | None:
        if not self._db_path or not self._db_path.exists():
            self._sql_status.setText("Database file missing")
            return None
        if self._db_conn is None:
            self._db_conn = sqlite3.connect(
                f"file:{self._db_path}?mode=ro",
                uri=True,
                check_same_thread=False,
            )
            self._db_conn.row_factory = sqlite3.Row
        return self._db_conn

    def _run_sql(self) -> None:
        sql = self._sql_input.toPlainText().strip()
        if not sql:
            self._sql_status.setText("Enter a SELECT query")
            return
        lowered = sql.lstrip().lower()
        if not (lowered.startswith("select") or lowered.startswith("with")):
            self._sql_status.setText("Only SELECT queries are allowed")
            return
        conn = self._ensure_db()
        if conn is None:
            return
        try:
            cur = conn.execute(sql)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description or []]
        except sqlite3.Error as exc:
            self._sql_status.setText(str(exc))
            return

        self._sql_status.setText(f"{len(rows):,} rows")
        data = {
            "columns": columns,
            "rows": [list(row) for row in rows],
        }
        self._load_table_from_query(data)

    def _load_table_from_query(self, table: dict[str, Any]) -> None:
        columns: list[str] = table["columns"]
        rows: list[list[Any]] = table["rows"]

        self._source_model.clear()
        self._source_model.setHorizontalHeaderLabels(["Row"] + columns)

        for row_index, row_data in enumerate(rows, start=1):
            items: list[QStandardItem] = []
            row_item = QStandardItem(str(row_index))
            row_item.setEditable(False)
            row_item.setData(row_index, Qt.ItemDataRole.UserRole)
            items.append(row_item)
            for val in row_data:
                if val is None:
                    cell = QStandardItem("")
                    cell.setForeground(Qt.GlobalColor.gray)
                elif isinstance(val, bytes):
                    cell = QStandardItem(f"<BLOB {len(val):,} B>")
                    cell.setForeground(Qt.GlobalColor.blue)
                    cell.setData(val, Qt.ItemDataRole.UserRole)
                else:
                    cell = QStandardItem(str(val))
                if isinstance(val, (int, float)):
                    cell.setData(val, Qt.ItemDataRole.UserRole)
                cell.setEditable(False)
                items.append(cell)
            self._source_model.appendRow(items)

        self._table_view.resizeColumnsToContents()
        row_word = "row" if len(rows) == 1 else "rows"
        self._row_count_label.setText(f"({len(rows):,} {row_word})")

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                headers = [
                    self._source_model.headerData(i, Qt.Orientation.Horizontal)
                    for i in range(self._source_model.columnCount())
                ]
                writer.writerow(headers)
                for row in range(self._proxy_model.rowCount()):
                    row_values: list[str] = []
                    for col in range(self._proxy_model.columnCount()):
                        idx = self._proxy_model.index(row, col)
                        row_values.append(self._proxy_model.data(idx) or "")
                    writer.writerow(row_values)
            self._sql_status.setText(f"Exported: {path}")
        except Exception as exc:
            self._sql_status.setText(str(exc))

    def _on_context_menu(self, pos: object) -> None:
        index = self._table_view.indexAt(pos)
        if not index.isValid():
            return
        blob = self._table_view.model().data(index, Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        copy_cell = menu.addAction("Copy cell")
        copy_row = menu.addAction("Copy row (TSV)")
        copy_sel = menu.addAction("Copy selection (TSV)")
        blob_preview = menu.addAction("Preview BLOB")
        blob_hex = menu.addAction("Open BLOB in Hex")
        blob_export = menu.addAction("Export BLOB…")
        if not isinstance(blob, (bytes, bytearray)):
            blob_preview.setEnabled(False)
            blob_hex.setEnabled(False)
            blob_export.setEnabled(False)
        action = menu.exec(self._table_view.viewport().mapToGlobal(pos))
        if action == copy_cell:
            QApplication.clipboard().setText(str(self._table_view.model().data(index)))
        elif action == copy_row:
            self._copy_rows([index.row()])
        elif action == copy_sel:
            rows = sorted({i.row() for i in self._table_view.selectedIndexes()})
            self._copy_rows(rows)
        elif action == blob_preview:
            self._preview_blob(bytes(blob))
        elif action == blob_hex:
            self._open_blob_hex(bytes(blob))
        elif action == blob_export:
            self._export_blob(bytes(blob))

    def _copy_rows(self, rows: list[int]) -> None:
        lines: list[str] = []
        for row in rows:
            values = []
            for col in range(self._proxy_model.columnCount()):
                idx = self._proxy_model.index(row, col)
                values.append(str(self._proxy_model.data(idx) or ""))
            lines.append("\t".join(values))
        QApplication.clipboard().setText("\n".join(lines))

    def _open_blob_hex(self, blob: bytes) -> None:
        from crush.viewers.hex_viewer import HexViewer
        dialog = QDialog(self)
        dialog.setWindowTitle(f"BLOB Hex ({len(blob):,} B)")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        viewer = HexViewer(blob, dialog)
        layout.addWidget(viewer)
        dialog.resize(900, 600)
        dialog.exec()

    def _export_blob(self, blob: bytes) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export BLOB", "", "All files (*)")
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(blob)
            self._sql_status.setText(f"BLOB exported: {path}")
        except Exception as exc:
            self._sql_status.setText(str(exc))

    def _preview_blob(self, blob: bytes) -> None:
        # Try image first
        try:
            from PySide6.QtGui import QPixmap
            pixmap = QPixmap()
            if pixmap.loadFromData(blob):
                dialog = QDialog(self)
                dialog.setWindowTitle(f"BLOB Preview ({len(blob):,} B)")
                layout = QVBoxLayout(dialog)
                label = QLabel()
                label.setPixmap(pixmap)
                layout.addWidget(label)
                dialog.resize(800, 600)
                dialog.exec()
                return
        except Exception:
            pass

        # Try text (utf-8 with fallback)
        try:
            text = blob.decode("utf-8")
        except Exception:
            try:
                text = blob.decode("latin-1")
            except Exception:
                text = ""

        if text:
            dialog = QDialog(self)
            dialog.setWindowTitle(f"BLOB Preview (text, {len(blob):,} B)")
            layout = QVBoxLayout(dialog)
            viewer = QPlainTextEdit()
            viewer.setReadOnly(True)
            viewer.setPlainText(text[:200_000])
            layout.addWidget(viewer)
            dialog.resize(900, 600)
            dialog.exec()
            return

        # Fallback to hex
        self._open_blob_hex(blob)

    def keyPressEvent(self, event: object) -> None:  # type: ignore[override]
        if hasattr(event, "matches") and event.matches(QKeySequence.StandardKey.Copy):
            rows = sorted({i.row() for i in self._table_view.selectedIndexes()})
            if not rows and self._table_view.currentIndex().isValid():
                rows = [self._table_view.currentIndex().row()]
            if rows:
                self._copy_rows(rows)
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def closeEvent(self, event: object) -> None:  # type: ignore[override]
        if self._db_conn is not None:
            self._db_conn.close()
            self._db_conn = None
        if self._db_path and self._db_path.exists():
            try:
                self._db_path.unlink()
            except Exception:
                pass
        super().closeEvent(event)  # type: ignore[arg-type]


class _NumericSortProxy(QSortFilterProxyModel):
    def lessThan(self, left, right) -> bool:  # type: ignore[override]
        left_data = self.sourceModel().data(left, Qt.ItemDataRole.UserRole)
        right_data = self.sourceModel().data(right, Qt.ItemDataRole.UserRole)
        if isinstance(left_data, (int, float)) and isinstance(right_data, (int, float)):
            return left_data < right_data
        return super().lessThan(left, right)
