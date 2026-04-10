# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Table viewer — displays SQLite tables as a sortable, searchable grid."""
from __future__ import annotations

from typing import Any

import csv
import sqlite3
from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QKeySequence, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
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

from crush.core.formatters import (
    bytes_to_hexview,
    pretty_object,
    try_base64_text,
    try_plist_text,
    try_xml_text,
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
    open_bytes_requested = Signal(bytes, str)
    def __init__(self, data: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data = data
        db_path_value = data.get("__db_path") if isinstance(data, dict) else None
        if isinstance(db_path_value, str) and db_path_value:
            candidate = Path(db_path_value)
            self._db_path = candidate if candidate.is_file() else None
        else:
            self._db_path = None
        self._db_conn: sqlite3.Connection | None = None
        self._summary_label = "Summary (generated)"
        self._build_ui()
        if data:
            table_names = [k for k in data.keys() if not k.startswith("__")]
            if self._db_path:
                self._table_combo.clear()
                self._table_combo.addItem(self._summary_label)
                self._table_combo.addItems(table_names)
                self._load_summary()
            else:
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
        if table_name == self._summary_label:
            self._load_summary()
            return
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
                elif isinstance(val, (bytes, bytearray, memoryview)):
                    blob = val if isinstance(val, bytes) else bytes(val)
                    cell = QStandardItem(f"<BLOB {len(blob):,} B>")
                    cell.setForeground(Qt.GlobalColor.blue)
                    cell.setData(blob, Qt.ItemDataRole.UserRole)
                else:
                    cell = QStandardItem(str(val))
                if isinstance(val, (int, float)):
                    try:
                        cell.setData(val, Qt.ItemDataRole.UserRole)
                    except (OverflowError, Exception):
                        pass
                cell.setEditable(False)
                items.append(cell)
            self._source_model.appendRow(items)

        self._table_view.resizeColumnsToContents()
        table_meta = self._data.get(table_name, {}) if isinstance(self._data, dict) else {}
        was_truncated = isinstance(table_meta, dict) and table_meta.get("truncated", False)
        row_word = "row" if len(rows) == 1 else "rows"
        if was_truncated:
            self._row_count_label.setText(f"(first {len(rows):,} {row_word} — use SQL to load more)")
        else:
            self._row_count_label.setText(f"({len(rows):,} {row_word})")

    def _load_summary(self) -> None:
        """Show table list + row counts for SQLite databases."""
        conn = self._ensure_db()
        if conn is None:
            return
        cursor = conn.cursor()
        try:
            tables = [
                r[0]
                for r in cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            ]
        except Exception as exc:
            self._sql_status.setText(str(exc))
            return

        self._source_model.clear()
        self._source_model.setHorizontalHeaderLabels(["Table (generated)", "Rows"])
        self._sql_status.setText("Counting rows…")
        for table in tables:
            try:
                count = cursor.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]  # noqa: S608
            except Exception:
                count = "?"
            name_item = QStandardItem(table)
            name_item.setEditable(False)
            count_item = QStandardItem(str(count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            count_item.setEditable(False)
            if isinstance(count, int):
                count_item.setData(count, Qt.ItemDataRole.UserRole)
            self._source_model.appendRow([name_item, count_item])

        self._table_view.resizeColumnsToContents()
        word = "table" if len(tables) == 1 else "tables"
        self._row_count_label.setText(f"({len(tables):,} {word})")
        self._sql_status.setText(f"{len(tables):,} {word}")

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
                    try:
                        cell.setData(val, Qt.ItemDataRole.UserRole)
                    except (OverflowError, Exception):
                        pass
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
        blob_preview = menu.addAction("Inspect Cell…")
        blob_hex = menu.addAction("Open in Hex")
        blob_export = menu.addAction("Export…")
        open_tab = menu.addAction("Open as new tab")
        blob_bytes = _coerce_blob(blob)
        display_val = self._table_view.model().data(index, Qt.ItemDataRole.DisplayRole)
        has_display = display_val is not None and str(display_val) != ""
        if blob_bytes is None and not has_display:
            open_tab.setEnabled(False)
            blob_preview.setEnabled(False)
            blob_hex.setEnabled(False)
            blob_export.setEnabled(False)
            open_tab.setEnabled(False)
        if blob_bytes is None and has_display:
            blob_preview.setEnabled(True)
            blob_hex.setEnabled(True)
            blob_export.setEnabled(True)
        action = menu.exec(self._table_view.viewport().mapToGlobal(pos))
        if action == copy_cell:
            cell_val = self._table_view.model().data(index, Qt.ItemDataRole.UserRole)
            blob_bytes = _coerce_blob(cell_val)
            if blob_bytes is not None:
                QApplication.clipboard().setText(blob_bytes.hex())
            else:
                QApplication.clipboard().setText(str(self._table_view.model().data(index)))
        elif action == copy_row:
            self._copy_rows([index.row()])
        elif action == copy_sel:
            rows = sorted({i.row() for i in self._table_view.selectedIndexes()})
            self._copy_rows(rows)
        elif action == blob_preview:
            if blob_bytes is not None:
                self._preview_blob(blob_bytes)
            elif has_display:
                self._preview_blob(str(display_val).encode("utf-8", errors="replace"))
        elif action == blob_hex:
            if blob_bytes is not None:
                self._open_blob_hex(blob_bytes)
            elif has_display:
                self._open_blob_hex(str(display_val).encode("utf-8", errors="replace"))
        elif action == blob_export:
            if blob_bytes is not None:
                self._export_blob(blob_bytes)
            elif has_display:
                self._export_blob(str(display_val).encode("utf-8", errors="replace"))
        elif action == open_tab:
            data_to_open = blob_bytes
            if data_to_open is None and has_display:
                data_to_open = str(display_val).encode("utf-8", errors="replace")
            if data_to_open is not None:
                col_header = self._table_view.model().headerData(
                    index.column(), Qt.Orientation.Horizontal
                ) or "blob"
                self.open_bytes_requested.emit(data_to_open, str(col_header))

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
        dialog = _BlobInspector(blob, self)
        dialog.exec()

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
        # Also handle TEXT columns that store numeric-looking strings (SQLite TEXT
        # affinity returns Python str, so no UserRole is set for those values).
        left_str = self.sourceModel().data(left, Qt.ItemDataRole.DisplayRole) or ""
        right_str = self.sourceModel().data(right, Qt.ItemDataRole.DisplayRole) or ""
        try:
            return float(left_str) < float(right_str)
        except (ValueError, TypeError):
            pass
        return super().lessThan(left, right)


class _BlobInspector(QDialog):
    def __init__(self, blob: bytes, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._blob = blob
        self._build_ui()
        self._apply_view()

    def _build_ui(self) -> None:
        self.setWindowTitle(f"BLOB Inspector ({len(self._blob):,} B)")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(6)

        top_layout.addWidget(QLabel("Open as:"))
        self._format = QComboBox()
        self._format.addItems([
            "Auto",
            "Hex",
            "UTF-8 text",
            "Latin-1 text",
            "Base64 (decode)",
            "Plist / bplist",
            "XML",
        ])
        self._format.currentIndexChanged.connect(self._apply_view)
        top_layout.addWidget(self._format)

        self._copy_btn = QPushButton("Copy")
        self._copy_btn.clicked.connect(self._copy_current)
        top_layout.addWidget(self._copy_btn)
        top_layout.addStretch()
        layout.addWidget(top)

        self._viewer = QPlainTextEdit()
        self._viewer.setReadOnly(True)
        self._viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._viewer, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply_view(self) -> None:
        fmt = self._format.currentText()
        content = ""
        if fmt == "Auto":
            content = (
                self._try_plist()
                or self._try_xml()
                or self._try_utf8()
                or self._try_latin1()
                or self._hex()
            )
        elif fmt == "Hex":
            content = self._hex()
        elif fmt == "UTF-8 text":
            content = self._try_utf8() or "[decode error]"
        elif fmt == "Latin-1 text":
            content = self._try_latin1() or "[decode error]"
        elif fmt == "Base64 (decode)":
            content = self._try_base64() or "[decode error]"
        elif fmt == "Plist / bplist":
            content = self._try_plist() or "[parse error]"
        elif fmt == "XML":
            content = self._try_xml() or "[parse error]"
        self._viewer.setPlainText(content[:500_000])

    def _copy_current(self) -> None:
        QApplication.clipboard().setText(self._viewer.toPlainText())

    def _hex(self) -> str:
        return _bytes_to_hexview(self._blob, max_bytes=200_000)

    def _try_utf8(self) -> str:
        try:
            return self._blob.decode("utf-8")
        except Exception:
            return ""

    def _try_latin1(self) -> str:
        try:
            return self._blob.decode("latin-1")
        except Exception:
            return ""

    def _try_base64(self) -> str:
        return try_base64_text(self._blob) or ""

    def _try_plist(self) -> str:
        return try_plist_text(self._blob) or ""

    def _try_xml(self) -> str:
        return try_xml_text(self._blob) or ""


def _pretty(obj: object) -> str:
    return pretty_object(obj)


def _bytes_to_hexview(b: bytes, width: int = 16, max_bytes: int = 200_000) -> str:
    return bytes_to_hexview(b, width=width, max_bytes=max_bytes)


def _coerce_blob(value: object) -> bytes | None:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    return None
