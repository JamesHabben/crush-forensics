# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Table viewer — displays SQLite tables as a sortable, searchable grid."""
from __future__ import annotations

from typing import Any

import csv
import sqlite3
import struct
from collections import Counter
from pathlib import Path

from PySide6.QtCore import QRegularExpression, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QFont,
    QKeyEvent,
    QKeySequence,
    QStandardItem,
    QStandardItemModel,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
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
    QSplitter,
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
from crush.core.sqlite_wal import (
    build_page_table_map,
    parse_table_leaf_page,
)
from crush.core.ts_decode import TS_FORMATS as _TS_FORMATS
from crush.core.ts_decode import decode_ts as _decode_ts


def _wal_diag(db_path: "str | None", parser_diag: str = "") -> str:
    """Return a short diagnostic string explaining why WAL parsing failed."""
    if db_path is None:
        return "db_path is None"
    wal_path = Path(str(db_path) + "-wal")
    if not wal_path.exists():
        suffix = f" (parser: {parser_diag})" if parser_diag else ""
        return f"WAL file not found at temp path{suffix}"
    size = wal_path.stat().st_size
    if size < 32:
        suffix = f" — parser: {parser_diag}" if parser_diag else ""
        return f"WAL too small ({size} B){suffix}"
    try:
        magic = struct.unpack_from(">I", wal_path.read_bytes(), 0)[0]
    except Exception as exc:
        return f"read error: {exc}"
    if magic not in _WAL_MAGIC:
        return f"invalid magic 0x{magic:08x}"
    return f"WAL ok (size={size} B, magic=0x{magic:08x}) — frames list empty"


class _SqlHighlighter(QSyntaxHighlighter):
    _KEYWORDS = (
        "SELECT FROM WHERE INSERT UPDATE DELETE CREATE DROP TABLE VIEW INDEX TRIGGER "
        "JOIN LEFT RIGHT INNER OUTER CROSS ON AS AND OR NOT IN IS NULL LIKE GLOB "
        "LIMIT OFFSET ORDER BY GROUP HAVING DISTINCT UNION ALL WITH PRAGMA BETWEEN "
        "CASE WHEN THEN ELSE END EXISTS PRIMARY KEY FOREIGN REFERENCES UNIQUE "
        "INTO VALUES SET BEGIN COMMIT ROLLBACK REPLACE UPSERT RETURNING "
        "COUNT SUM AVG MIN MAX COALESCE IFNULL NULLIF CAST TYPEOF LENGTH "
        "SUBSTR TRIM UPPER LOWER DATE TIME DATETIME STRFTIME"
    ).split()

    def __init__(self, document: object) -> None:
        super().__init__(document)
        is_dark = QApplication.palette().window().color().lightness() < 128

        def fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.Bold)
            if italic:
                f.setFontItalic(True)
            return f

        if is_dark:
            kw  = fmt("#569cd6", bold=True)
            str_ = fmt("#ce9178")
            num  = fmt("#b5cea8")
            cmt  = fmt("#6a9955", italic=True)
        else:
            kw  = fmt("#0000cc", bold=True)
            str_ = fmt("#a31515")
            num  = fmt("#098658")
            cmt  = fmt("#008000", italic=True)

        ci = QRegularExpression.PatternOption.CaseInsensitiveOption
        kw_rx = r"\b(?:" + "|".join(self._KEYWORDS) + r")\b"
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = [
            (QRegularExpression(kw_rx, ci),         kw),
            (QRegularExpression(r"'(?:[^'\\]|\\.)*'"),  str_),
            (QRegularExpression(r'"(?:[^"\\]|\\.)*"'),  str_),
            (QRegularExpression(r"\[([^\]]*)\]"),        str_),
            (QRegularExpression(r"\b\d+\.?\d*\b"),       num),
            (QRegularExpression(r"--[^\n]*"),            cmt),
        ]

    def highlightBlock(self, text: str) -> None:
        for rx, fmt in self._rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


class _SqlEditor(QPlainTextEdit):
    """Plain-text SQL editor that emits run_requested on F5."""

    run_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_F5:
            self.run_requested.emit()
        else:
            super().keyPressEvent(event)


_WAL_MAGIC = (0x377F0682, 0x377F0683)

# (pragma, display label, kind, enum_map | None, description)
# kind values: "int" | "bool" | "enum" | "str"
_PRAGMA_CATALOG: list[tuple[str, str, str, dict[int, str] | None, str]] = [
    # File format
    ("application_id",     "Application ID",           "int",  None,
     "32-bit magic number identifying the application that created this database"),
    ("user_version",       "User version",             "int",  None,
     "Application-defined schema version number"),
    ("schema_version",     "Schema version",           "int",  None,
     "Internal counter incremented on every schema change"),
    ("data_version",       "Data version",             "int",  None,
     "Increments on any write; compare across connections to detect changes"),
    ("encoding",           "Encoding",                 "str",  None,
     "Text encoding for all string data in this database"),
    ("page_size",          "Page size (B)",            "int",  None,
     "Size of each B-tree page; fixed at database creation time"),
    ("page_count",         "Page count",               "int",  None,
     "Total allocated pages; multiply by page_size to get expected file size"),
    ("freelist_count",     "Free pages",               "int",  None,
     "Unallocated pages that may contain deleted data — forensically significant"),
    ("max_page_count",     "Max page count",           "int",  None,
     "Upper limit on database size in pages (0 = default limit)"),
    # Journal / safety
    ("journal_mode",       "Journal mode",             "str",  None,
     "Rollback journal strategy (delete / wal / truncate / persist / memory / off)"),
    ("journal_size_limit", "Journal size limit (B)",   "int",  None,
     "Maximum journal file size in bytes; -1 = unlimited"),
    ("synchronous",        "Synchronous",              "enum",
     {0: "OFF", 1: "NORMAL", 2: "FULL", 3: "EXTRA"},
     "How aggressively SQLite flushes writes to disk"),
    ("locking_mode",       "Locking mode",             "str",  None,
     "File locking strategy (NORMAL or EXCLUSIVE)"),
    ("wal_autocheckpoint", "WAL autocheckpoint (pages)", "int", None,
     "Pages accumulated in WAL file before automatic checkpoint is triggered"),
    # Vacuum / storage
    ("auto_vacuum",        "Auto vacuum",              "enum",
     {0: "NONE", 1: "FULL", 2: "INCREMENTAL"},
     "Automatic reclamation of free pages after DELETE"),
    ("secure_delete",      "Secure delete",            "enum",
     {0: "OFF", 1: "ON", 2: "FAST"},
     "Overwrite deleted content with zeros before freeing pages"),
    ("temp_store",         "Temp store",               "enum",
     {0: "DEFAULT", 1: "FILE", 2: "MEMORY"},
     "Storage location for temporary tables and indexes"),
    ("mmap_size",          "Memory-mapped I/O (B)",    "int",  None,
     "Maximum bytes used for memory-mapped I/O (0 = disabled)"),
    # Schema / safety flags
    ("foreign_keys",          "Foreign keys",          "bool", None,
     "Whether foreign key constraints are enforced"),
    ("recursive_triggers",    "Recursive triggers",    "bool", None,
     "Allow trigger bodies to fire additional triggers"),
    ("automatic_index",       "Automatic index",       "bool", None,
     "Query planner may create transient covering indexes"),
    ("trusted_schema",        "Trusted schema",        "bool", None,
     "Allow SQL functions in schema objects (security-relevant setting)"),
    ("read_uncommitted",      "Read uncommitted",      "bool", None,
     "Read without waiting for shared-cache write locks"),
    ("defer_foreign_keys",    "Defer foreign keys",    "bool", None,
     "Delay FK enforcement until end of outermost transaction"),
    ("query_only",            "Query only",            "bool", None,
     "Prevents any data modification in this connection"),
    # Cache (included for completeness)
    ("cache_size",            "Cache size (pages)",    "int",  None,
     "Pages kept in the in-memory page cache; negative value = KiB"),
]


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
    def __init__(
        self,
        data: dict[str, Any],
        parent: QWidget | None = None,
        show_db_tabs: bool = True,
    ) -> None:
        super().__init__(parent)
        self._data = data
        self._show_db_tabs = show_db_tabs
        self._col_ts_formats: dict[int, str] = {}
        db_path_value = data.get("__db_path") if isinstance(data, dict) else None
        if isinstance(db_path_value, str) and db_path_value:
            candidate = Path(db_path_value)
            self._db_path = candidate if candidate.is_file() else None
        else:
            self._db_path = None
        self._db_conn: sqlite3.Connection | None = None
        self._summary_label = "Summary (generated)"
        self._db_structure_label = "DB Structure (generated)"
        self._db_info_label = "DB Info (generated)"
        self._wal_label = "WAL Frames (generated)"
        self._wal_frames_cache: list[dict] | None = None
        self._wal_page_size: int = 0
        self._page_table_map: dict[int, str] = {}  # page_num → table_name
        self._build_ui()
        if data:
            table_names = [k for k in data.keys() if not k.startswith("__")]
            if self._db_path:
                self._table_combo.clear()
                if show_db_tabs:
                    self._table_combo.addItem(self._summary_label)
                    self._table_combo.addItem(self._db_structure_label)
                    self._table_combo.addItem(self._db_info_label)
                    if self._db_path and Path(str(self._db_path) + "-wal").exists():
                        self._table_combo.addItem(self._wal_label)
                self._table_combo.addItems(table_names)
                if show_db_tabs:
                    conn = self._ensure_db()
                    if conn:
                        try:
                            view_names = [
                                r[0] for r in conn.execute(
                                    "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
                                ).fetchall()
                            ]
                            if view_names:
                                self._table_combo.insertSeparator(self._table_combo.count())
                                self._table_combo.addItems(view_names)
                        except Exception:
                            pass
                    self._load_summary()
                else:
                    if table_names:
                        self._load_table(table_names[0])
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

        self._wal_toggle = QCheckBox("Show WAL history")
        self._wal_toggle.setVisible(False)
        self._wal_toggle.stateChanged.connect(self._on_wal_toggle)
        toolbar_layout.addWidget(self._wal_toggle)

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

        # SQL section: input row + status row below
        sql_bar = QWidget()
        sql_outer = QVBoxLayout(sql_bar)
        sql_outer.setContentsMargins(8, 4, 8, 2)
        sql_outer.setSpacing(2)

        sql_row = QWidget()
        sql_layout = QHBoxLayout(sql_row)
        sql_layout.setContentsMargins(0, 0, 0, 0)
        sql_layout.setSpacing(8)
        sql_layout.addWidget(QLabel("SQL:"))
        self._sql_input = _SqlEditor()
        self._sql_input.run_requested.connect(self._run_sql)
        self._sql_input.setPlaceholderText("SELECT * FROM table LIMIT 100;")
        line_h = self._sql_input.fontMetrics().lineSpacing()
        self._sql_input.setMinimumHeight(line_h * 3)
        self._sql_input.setFixedHeight(line_h * 6 + 8)
        self._sql_highlighter = _SqlHighlighter(self._sql_input.document())
        sql_layout.addWidget(self._sql_input, stretch=1)
        self._run_sql_btn = QPushButton("Run")
        self._run_sql_btn.clicked.connect(self._run_sql)
        sql_layout.addWidget(self._run_sql_btn)
        self._export_btn = QPushButton("Export CSV…")
        self._export_btn.clicked.connect(self._export_csv)
        sql_layout.addWidget(self._export_btn)
        sql_outer.addWidget(sql_row)

        self._sql_status = QLabel("")
        self._sql_status.setContentsMargins(4, 0, 0, 2)
        sql_outer.addWidget(self._sql_status)

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
        self._table_view.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table_view.horizontalHeader().customContextMenuRequested.connect(self._on_header_context_menu)
        self._table_view.verticalHeader().setDefaultSectionSize(22)
        self._table_view.doubleClicked.connect(self._on_table_double_clicked)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(sql_bar)
        splitter.addWidget(self._table_view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([140, 500])
        layout.addWidget(splitter, stretch=1)

    def _load_table(self, table_name: str) -> None:
        """Populate the model with the selected table's data."""
        if table_name == self._summary_label:
            self._load_summary()
            return
        if table_name == self._db_structure_label:
            self._load_db_structure()
            return
        if table_name == self._db_info_label:
            self._load_db_info()
            return
        if table_name == self._wal_label:
            self._wal_toggle.setVisible(False)
            self._load_wal_frames()
            return
        table = self._data.get(table_name)
        if table is None:
            # Not pre-loaded (e.g. a view) — query live from the DB
            conn = self._ensure_db()
            if conn is None:
                return
            try:
                cur = conn.execute(f"SELECT * FROM [{table_name}] LIMIT 10001")  # noqa: S608
                raw_rows = cur.fetchall()
                was_truncated = len(raw_rows) > 10_000
                table = {
                    "columns": [d[0] for d in cur.description or []],
                    "rows": [list(r) for r in raw_rows[:10_000]],
                    "truncated": was_truncated,
                }
            except Exception as exc:
                self._sql_status.setStyleSheet("color: red;")
                self._sql_status.setText(str(exc))
                return

        # Ensure _page_table_map is populated before checking has_wal (cached after first call)
        self._get_wal_frames()

        # Show WAL toggle only for real tables that have WAL data
        has_wal = bool(self._page_table_map) and any(
            v == table_name for v in self._page_table_map.values()
        )
        self._wal_toggle.setVisible(has_wal)

        self._col_ts_formats.clear()
        columns: list[str] = table["columns"]
        rows: list[list[Any]] = table["rows"]

        self._source_model.clear()
        show_wal = has_wal and self._wal_toggle.isChecked()
        headers = ["Row"] + columns + (["WAL Source"] if show_wal else [])
        self._source_model.setHorizontalHeaderLabels(headers)

        def _append_row(row_data: list[Any], source_label: str | None = None,
                        row_color: object = None) -> None:
            row_index = self._source_model.rowCount() + 1
            row_item = QStandardItem(str(row_index))
            row_item.setEditable(False)
            row_item.setData(row_index, Qt.ItemDataRole.UserRole)
            if row_color:
                row_item.setForeground(row_color)
            items = [row_item]
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
                    if row_color:
                        cell.setForeground(row_color)
                if isinstance(val, (int, float)):
                    try:
                        cell.setData(val, Qt.ItemDataRole.UserRole)
                    except (OverflowError, Exception):
                        pass
                cell.setEditable(False)
                items.append(cell)
            if show_wal:
                src = QStandardItem(source_label or "current")
                src.setEditable(False)
                if row_color:
                    src.setForeground(row_color)
                items.append(src)
            self._source_model.appendRow(items)

        for row_data in rows:
            _append_row(row_data)

        wal_row_count = 0
        if show_wal:
            wal_row_count = self._inject_wal_rows(table_name, columns, _append_row)

        self._table_view.resizeColumnsToContents()
        table_meta = self._data.get(table_name, {}) if isinstance(self._data, dict) else {}
        was_truncated = isinstance(table_meta, dict) and table_meta.get("truncated", False)
        total = len(rows)
        row_word = "row" if total == 1 else "rows"
        label = f"(first {total:,} {row_word} — use SQL to load more)" if was_truncated \
            else f"({total:,} {row_word})"
        if wal_row_count:
            label += f"  +{wal_row_count} from WAL"
        self._row_count_label.setText(label)

    def _inject_wal_rows(
        self,
        table_name: str,
        columns: list[str],
        append_row: object,
    ) -> int:
        """Parse non-Active WAL frames for *table_name* and inject their rows.

        Returns the number of rows injected.
        """
        frames = self._get_wal_frames()
        if not frames or self._db_path is None or self._wal_page_size == 0:
            return 0

        _status_color: dict[str, object] = {
            "Superseded":  QColor("#cc8800"),
            "Uncommitted": QColor("#4488ff"),
            "WAL slack":   Qt.GlobalColor.darkGray,
        }

        try:
            wal_data = Path(str(self._db_path) + "-wal").read_bytes()
        except OSError:
            return 0

        injected = 0
        for f in frames:
            if f["status"] == "Active":
                continue
            if self._page_table_map.get(f["page"]) != table_name:
                continue

            page_start = f["offset"] + 24
            page_bytes = wal_data[page_start: page_start + self._wal_page_size]
            parsed = parse_table_leaf_page(page_bytes)
            if not parsed:
                continue

            color = _status_color.get(f["status"])
            label = f"WAL {f['status']} (frame {f['frame']})"
            n_cols = len(columns)
            for _rowid, values in parsed:
                padded: list[Any] = (values + [None] * n_cols)[:n_cols]
                append_row(padded, label, color)  # type: ignore[operator]
                injected += 1

        return injected

    def _on_wal_toggle(self, _state: int) -> None:
        """Re-load the current table when the WAL history toggle changes."""
        current = self._table_combo.currentText()
        if current and current not in (
            self._summary_label,
            self._db_structure_label,
            self._db_info_label,
            self._wal_label,
        ):
            self._load_table(current)

    def _load_summary(self) -> None:
        """Show tables and views with row counts; label includes full schema object counts."""
        conn = self._ensure_db()
        if conn is None:
            return
        cursor = conn.cursor()
        try:
            rows_tv = cursor.execute(
                "SELECT name, type FROM sqlite_master "
                "WHERE type IN ('table', 'view') ORDER BY type, name"
            ).fetchall()
            counts = dict(
                cursor.execute(
                    "SELECT type, COUNT(*) FROM sqlite_master "
                    "WHERE type IN ('table', 'view', 'index', 'trigger') GROUP BY type"
                ).fetchall()
            )
        except Exception as exc:
            self._sql_status.setStyleSheet("color: red;")
            self._sql_status.setText(str(exc))
            return

        self._source_model.clear()
        self._source_model.setHorizontalHeaderLabels(["Name (generated)", "Type", "Rows"])
        self._sql_status.setStyleSheet("")

        for name, obj_type in rows_tv:
            try:
                count = cursor.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]  # noqa: S608
            except Exception:
                count = "?"
            name_item = QStandardItem(name)
            name_item.setEditable(False)
            type_item = QStandardItem(obj_type)
            type_item.setEditable(False)
            row_word = "row" if count == 1 else "rows"
            count_text = f"{count:,} {row_word}" if isinstance(count, int) else "?"
            count_item = QStandardItem(count_text)
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            count_item.setEditable(False)
            if isinstance(count, int):
                count_item.setData(count, Qt.ItemDataRole.UserRole)
            self._source_model.appendRow([name_item, type_item, count_item])

        self._table_view.resizeColumnsToContents()

        def _c(key: str) -> int:
            return counts.get(key, 0)

        parts = [
            f"{_c('table')} table{'s' if _c('table') != 1 else ''}",
            f"{_c('view')} view{'s' if _c('view') != 1 else ''}",
            f"{_c('index')} index{'es' if _c('index') != 1 else ''}",
            f"{_c('trigger')} trigger{'s' if _c('trigger') != 1 else ''}",
        ]
        summary = ", ".join(parts)
        self._row_count_label.setText(f"({summary})")
        self._sql_status.setText(summary)

    def _load_db_structure(self) -> None:
        """Show all schema objects (tables, views, indexes, triggers) with structural info."""
        conn = self._ensure_db()
        if conn is None:
            return
        cursor = conn.cursor()
        try:
            objects = cursor.execute(
                "SELECT name, type, tbl_name, sql FROM sqlite_master "
                "WHERE type IN ('table', 'view', 'index', 'trigger') ORDER BY type, name"
            ).fetchall()
        except Exception as exc:
            self._sql_status.setStyleSheet("color: red;")
            self._sql_status.setText(str(exc))
            return

        self._source_model.clear()
        self._source_model.setHorizontalHeaderLabels(["Name (generated)", "Type", "Info"])
        self._sql_status.setStyleSheet("")

        for name, obj_type, tbl_name, sql in objects:
            name_item = QStandardItem(name)
            name_item.setEditable(False)
            type_item = QStandardItem(obj_type)
            type_item.setEditable(False)

            if obj_type == "table":
                try:
                    cols = cursor.execute(f"PRAGMA table_info([{name}])").fetchall()
                    col_names = ", ".join(r[1] for r in cols)
                    info_text = f"({col_names})"
                except Exception:
                    info_text = ""
            elif obj_type == "view":
                info_text = (sql or "").replace("\n", " ").strip()
            elif obj_type == "index":
                try:
                    idx_rows = cursor.execute(f"PRAGMA index_info([{name}])").fetchall()
                    cols = ", ".join(r[2] for r in idx_rows if r[2]) or "(expression)"
                    info_text = f"ON {tbl_name} ({cols})"
                except Exception:
                    info_text = f"ON {tbl_name}"
            elif obj_type == "trigger":
                first_line = (sql or "").split("\n")[0].strip()
                info_text = first_line if first_line else f"ON {tbl_name}"
            else:
                info_text = ""

            info_item = QStandardItem(info_text)
            info_item.setEditable(False)
            self._source_model.appendRow([name_item, type_item, info_item])

        self._table_view.resizeColumnsToContents()
        total = self._source_model.rowCount()
        word = "object" if total == 1 else "objects"
        self._row_count_label.setText(f"({total} schema {word})")
        self._sql_status.setText("")

    def _get_wal_frames(self) -> list[dict] | None:
        """Parse WAL file and return classified frame list (cached)."""
        if self._wal_frames_cache is not None:
            return self._wal_frames_cache
        if self._db_path is None:
            return None
        wal_path = Path(str(self._db_path) + "-wal")
        if not wal_path.exists():
            return None
        try:
            data = wal_path.read_bytes()
        except OSError:
            return None
        if len(data) < 32:
            return None

        magic = struct.unpack_from(">I", data, 0)[0]
        if magic not in _WAL_MAGIC:
            return None

        page_size = struct.unpack_from(">I", data, 8)[0]
        self._wal_page_size = page_size
        salt1     = struct.unpack_from(">I", data, 16)[0]
        salt2     = struct.unpack_from(">I", data, 20)[0]

        frame_size = 24 + page_size
        offset = 32
        raw: list[dict] = []

        while offset + frame_size <= len(data):
            page_num = struct.unpack_from(">I", data, offset)[0]
            db_size  = struct.unpack_from(">I", data, offset + 4)[0]
            f_salt1  = struct.unpack_from(">I", data, offset + 8)[0]
            f_salt2  = struct.unpack_from(">I", data, offset + 12)[0]
            raw.append({
                "frame":     len(raw) + 1,
                "page":      page_num,
                "db_size":   db_size,
                "is_commit": db_size > 0,
                "salt_ok":   f_salt1 == salt1 and f_salt2 == salt2,
                "offset":    offset,
                "tx":        None,
                "status":    "",
            })
            offset += frame_size

        # Assign transaction numbers to salt-valid frames
        tx = 0
        for f in raw:
            if not f["salt_ok"]:
                continue
            f["tx"] = tx + 1
            if f["is_commit"]:
                tx += 1

        # Find last committed frame index (salt-valid + is_commit)
        last_commit_idx = -1
        for i, f in enumerate(raw):
            if f["salt_ok"] and f["is_commit"]:
                last_commit_idx = i

        # For committed range: track last occurrence of each page → active
        page_latest: dict[int, int] = {}
        for i, f in enumerate(raw):
            if f["salt_ok"] and i <= last_commit_idx:
                page_latest[f["page"]] = i

        # Classify
        for i, f in enumerate(raw):
            if not f["salt_ok"]:
                f["status"] = "WAL slack"
            elif i > last_commit_idx:
                f["status"] = "Uncommitted"
            elif page_latest.get(f["page"]) == i:
                f["status"] = "Active"
            else:
                f["status"] = "Superseded"

        self._wal_frames_cache = raw

        # Build page→table map (best-effort; silently ignore errors)
        conn = self._ensure_db()
        if conn is not None:
            try:
                self._page_table_map = build_page_table_map(conn, data, page_size)
            except Exception:
                self._page_table_map = {}

        return raw

    def _load_wal_frames(self) -> None:
        """Show full WAL frame inventory."""
        frames = self._get_wal_frames()
        self._source_model.clear()
        self._source_model.setHorizontalHeaderLabels(
            ["Frame", "Page", "Transaction", "Status", "Table", "Offset (B)"]
        )
        if not frames:
            parser_diag = self._data.get("__wal_diag", "") if isinstance(self._data, dict) else ""
            diag = _wal_diag(self._db_path, parser_diag)
            item = QStandardItem(f"No WAL file found or format not recognised — {diag}")
            item.setEditable(False)
            self._source_model.appendRow([item])
            self._row_count_label.setText("")
            return

        _status_color: dict[str, object] = {
            "Superseded":  QColor("#cc8800"),
            "Uncommitted": QColor("#4488ff"),
            "WAL slack":   Qt.GlobalColor.darkGray,
        }

        for f in frames:
            color = _status_color.get(f["status"])
            table_name = self._page_table_map.get(f["page"], "—")

            def _item(text: str, sort_val: object = None, _c: object = color) -> QStandardItem:
                it = QStandardItem(text)
                it.setEditable(False)
                if sort_val is not None:
                    it.setData(sort_val, Qt.ItemDataRole.UserRole)
                if _c is not None:
                    it.setForeground(_c)
                return it

            self._source_model.appendRow([
                _item(str(f["frame"]),                   f["frame"]),
                _item(str(f["page"]),                    f["page"]),
                _item(str(f["tx"]) if f["tx"] else "—",  f["tx"] or 0),
                _item(f["status"]),
                _item(table_name),
                _item(str(f["offset"]),                  f["offset"]),
            ])

        self._table_view.resizeColumnsToContents()


        counts = Counter(f["status"] for f in frames)
        parts = [f"{len(frames)} total"]
        for status in ("Active", "Superseded", "Uncommitted", "WAL slack"):
            n = counts.get(status, 0)
            if n:
                parts.append(f"{n} {status.lower()}")
        self._row_count_label.setText(f"({', '.join(parts)})")
        self._sql_status.setText("Double-click a row to open the raw page in the hex viewer")

    def _on_table_double_clicked(self, index: object) -> None:
        """Double-click handler: open WAL frame page bytes in the hex viewer."""
        if self._table_combo.currentText() != self._wal_label:
            return
        if self._db_path is None or self._wal_page_size == 0:
            return

        row = self._proxy_model.mapToSource(self._proxy_model.index(index.row(), 0)).row()  # type: ignore[union-attr]

        def _user(col: int) -> object:
            return self._source_model.item(row, col).data(Qt.ItemDataRole.UserRole)

        frame_num = _user(0)
        page_num  = _user(1)
        offset    = _user(5)
        if offset is None:
            return

        wal_path = Path(str(self._db_path) + "-wal")
        try:
            wal_data = wal_path.read_bytes()
            page_start = int(offset) + 24  # skip 24-byte frame header
            page_bytes = wal_data[page_start : page_start + self._wal_page_size]
        except OSError:
            return

        if page_bytes:
            self.open_bytes_requested.emit(
                page_bytes,
                f"WAL frame {frame_num} — page {page_num}",
            )

    def _load_db_info(self) -> None:
        """Show all PRAGMA settings with decoded enum values and descriptions."""
        conn = self._ensure_db()
        if conn is None:
            return
        cursor = conn.cursor()
        self._source_model.clear()
        self._source_model.setHorizontalHeaderLabels(["Setting (generated)", "Value", "Description"])

        # WAL summary block (if present)
        frames = self._get_wal_frames()
        if frames is not None:

            counts = Counter(f["status"] for f in frames)

            def _wal_row(label: str, value: str, desc: str, color: object = None) -> None:
                s = QStandardItem(label)
                s.setEditable(False)
                v = QStandardItem(value)
                v.setEditable(False)
                d = QStandardItem(desc)
                d.setForeground(Qt.GlobalColor.gray)
                d.setEditable(False)
                if color is not None:
                    for item in (s, v):
                        item.setForeground(color)
                self._source_model.appendRow([s, v, d])

            wal_path = Path(str(self._db_path) + "-wal")
            wal_size = wal_path.stat().st_size if wal_path.exists() else 0
            _wal_row("WAL file size (B)",    f"{wal_size:,}",                  "Size of the -wal companion file on disk")
            _wal_row("WAL total frames",     str(len(frames)),                 "Total frames found in WAL file")
            _wal_row("WAL active frames",    str(counts.get("Active", 0)),     "Frames currently read by SQLite (newest per page)")
            n_sup = counts.get("Superseded", 0)
            _wal_row("WAL superseded frames", str(n_sup),
                     "Older versions of pages — may contain overwritten or deleted data",
                     QColor("#cc8800") if n_sup else None)
            n_unc = counts.get("Uncommitted", 0)
            _wal_row("WAL uncommitted frames", str(n_unc),
                     "Frames beyond the last commit marker — captured mid-transaction",
                     QColor("#4488ff") if n_unc else None)
            n_slack = counts.get("WAL slack", 0)
            _wal_row("WAL slack frames",     str(n_slack),
                     "Salt-mismatch frames from a previous WAL cycle — reused WAL space",
                     Qt.GlobalColor.darkGray if n_slack else None)

            # Visual separator
            sep = QStandardItem("─" * 30)
            sep.setForeground(Qt.GlobalColor.gray)
            sep.setEditable(False)
            self._source_model.appendRow([sep, QStandardItem(""), QStandardItem("")])

        for pragma, label, ptype, enum_map, description in _PRAGMA_CATALOG:
            try:
                row = cursor.execute(f"PRAGMA {pragma}").fetchone()
                raw = row[0] if row else None
            except Exception:
                raw = None

            if raw is None:
                display = "—"
            elif ptype == "bool":
                try:
                    iv = int(raw)
                    display = f"{iv} — {'ON' if iv else 'OFF'}"
                except (ValueError, TypeError):
                    display = str(raw)
            elif ptype == "enum" and enum_map:
                try:
                    iv = int(raw)
                    label_str = enum_map.get(iv, str(iv))
                    display = f"{iv} — {label_str}"
                except (ValueError, TypeError):
                    display = str(raw)
            else:
                display = str(raw)

            setting_item = QStandardItem(label)
            setting_item.setEditable(False)
            value_item = QStandardItem(display)
            value_item.setEditable(False)
            desc_item = QStandardItem(description)
            desc_item.setForeground(Qt.GlobalColor.gray)
            desc_item.setEditable(False)
            self._source_model.appendRow([setting_item, value_item, desc_item])

        hint_item = QStandardItem("Integrity check")
        hint_item.setEditable(False)
        hint_value = QStandardItem("→ run in SQL bar: PRAGMA integrity_check")
        hint_value.setForeground(Qt.GlobalColor.gray)
        hint_value.setEditable(False)
        hint_desc = QStandardItem("Scans database for corruption (can be slow on large files)")
        hint_desc.setForeground(Qt.GlobalColor.gray)
        hint_desc.setEditable(False)
        self._source_model.appendRow([hint_item, hint_value, hint_desc])

        self._table_view.resizeColumnsToContents()
        self._row_count_label.setText(f"({len(_PRAGMA_CATALOG)} settings)")
        self._sql_input.setPlainText("PRAGMA integrity_check;")
        self._sql_status.setText("")

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
        cursor = self._sql_input.textCursor()
        selected = cursor.selectedText().replace("", "\n").strip()
        sql = selected if selected else self._sql_input.toPlainText().strip()
        if not sql:
            self._sql_status.setStyleSheet("color: red;")
            self._sql_status.setText("Enter a SELECT or PRAGMA query")
            return
        lowered = sql.lstrip().lower()
        if not (lowered.startswith("select") or lowered.startswith("with") or lowered.startswith("pragma")):
            self._sql_status.setStyleSheet("color: red;")
            self._sql_status.setText("Only SELECT and PRAGMA queries are allowed")
            return
        conn = self._ensure_db()
        if conn is None:
            return
        try:
            cur = conn.execute(sql)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description or []]
        except sqlite3.Error as exc:
            self._sql_status.setStyleSheet("color: red;")
            self._sql_status.setText(str(exc))
            return

        self._sql_status.setStyleSheet("")
        word = "row" if len(rows) == 1 else "rows"
        self._sql_status.setText(f"{len(rows):,} {word} returned")
        data = {
            "columns": columns,
            "rows": [list(row) for row in rows],
        }
        self._load_table_from_query(data)

    def _load_table_from_query(self, table: dict[str, Any]) -> None:
        self._col_ts_formats.clear()
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
        try:
            blob = self._table_view.model().data(index, Qt.ItemDataRole.UserRole)
        except OverflowError:
            blob = None
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

    def _on_header_context_menu(self, pos: object) -> None:
        header = self._table_view.horizontalHeader()
        col = header.logicalIndexAt(pos)
        if col <= 0:  # column 0 is "Row" — skip
            return

        menu = QMenu(self)
        ts_submenu = menu.addMenu("Decode column as timestamp")
        fmt_actions: dict[object, str] = {}
        active = self._col_ts_formats.get(col)
        for key, label, _ in _TS_FORMATS:
            act = ts_submenu.addAction(label)
            act.setCheckable(True)
            act.setChecked(active == key)
            fmt_actions[act] = key

        menu.addSeparator()
        clear_act = menu.addAction("Clear timestamp format")
        clear_act.setEnabled(col in self._col_ts_formats)

        chosen = menu.exec(header.mapToGlobal(pos))
        if chosen in fmt_actions:
            self._col_ts_formats[col] = fmt_actions[chosen]
            self._apply_col_ts_format(col)
        elif chosen == clear_act:
            self._col_ts_formats.pop(col, None)
            self._revert_col_ts_format(col)

    def _apply_col_ts_format(self, col: int) -> None:
        fmt = self._col_ts_formats.get(col)
        if fmt is None:
            return
        for row in range(self._source_model.rowCount()):
            item = self._source_model.item(row, col)
            if item is None:
                continue
            raw = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(raw, (int, float)):
                continue
            decoded = _decode_ts(raw, fmt)
            if decoded is not None:
                item.setText(decoded)
        h_item = self._source_model.horizontalHeaderItem(col)
        if h_item is not None:
            base = h_item.data(Qt.ItemDataRole.UserRole) or h_item.text()
            h_item.setData(base, Qt.ItemDataRole.UserRole)
            suffix = next(s for k, _, s in _TS_FORMATS if k == fmt)
            h_item.setText(f"{base} [{suffix}]")

    def _revert_col_ts_format(self, col: int) -> None:
        for row in range(self._source_model.rowCount()):
            item = self._source_model.item(row, col)
            if item is None:
                continue
            raw = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(raw, (int, float)):
                item.setText(str(raw))
        h_item = self._source_model.horizontalHeaderItem(col)
        if h_item is not None:
            base = h_item.data(Qt.ItemDataRole.UserRole)
            if base:
                h_item.setText(str(base))

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
        try:
            left_data = self.sourceModel().data(left, Qt.ItemDataRole.UserRole)
            right_data = self.sourceModel().data(right, Qt.ItemDataRole.UserRole)
        except OverflowError:
            left_data = None
            right_data = None
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


# Column layout produced by bytes_to_hexview (e.g. "0000000a: 48 65 6c 6c 6f  Hello"):
# cols  0-7   offset (8 hex digits)
# col   8     ':'
# col   9     space
# cols 10-56  hex section (16 bytes × 3 − 1 = 47 chars, space-padded)
# cols 57-58  two spaces
# cols 59+    ASCII (up to 16 printable chars)
_BLOB_HEX_START = 10
_BLOB_HEX_END = 57
_BLOB_ASCII_START = 59


class _BlobViewerEdit(QPlainTextEdit):
    """QPlainTextEdit with a hex-aware context menu for the BLOB inspector."""

    def __init__(self, inspector: "_BlobInspector") -> None:
        super().__init__()
        self._inspector = inspector

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = self.createStandardContextMenu()
        cursor = self.textCursor()
        if cursor.hasSelection() and self._inspector._is_hex_mode():
            menu.addSeparator()
            menu.addAction("Copy Selected Hex").triggered.connect(
                self._inspector._copy_selected_hex
            )
            menu.addAction("Copy Selected ASCII").triggered.connect(
                self._inspector._copy_selected_ascii
            )
        menu.addSeparator()
        menu.addAction("Copy All").triggered.connect(self._inspector._copy_all)
        menu.exec(event.globalPos())


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

        self._viewer = _BlobViewerEdit(self)
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

    def _is_hex_mode(self) -> bool:
        fmt = self._format.currentText()
        return fmt in ("Hex", "Auto")

    def _copy_current(self) -> None:
        QApplication.clipboard().setText(self._viewer.toPlainText())

    def _copy_all(self) -> None:
        QApplication.clipboard().setText(self._viewer.toPlainText())

    def _copy_selected_hex(self) -> None:
        cursor = self._viewer.textCursor()
        if not cursor.hasSelection():
            return
        text = cursor.selectedText()
        tokens: list[str] = []
        for line in text.split("\u2029"):
            hex_section = line[_BLOB_HEX_START:_BLOB_HEX_END]
            for part in hex_section.split():
                if len(part) == 2 and all(c in "0123456789ABCDEFabcdef" for c in part):
                    tokens.append(part.upper())
        QApplication.clipboard().setText(" ".join(tokens))

    def _copy_selected_ascii(self) -> None:
        cursor = self._viewer.textCursor()
        if not cursor.hasSelection():
            return
        text = cursor.selectedText()
        parts: list[str] = []
        for line in text.split("\u2029"):
            if len(line) > _BLOB_ASCII_START:
                parts.append(line[_BLOB_ASCII_START:])
        QApplication.clipboard().setText("".join(parts))

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
