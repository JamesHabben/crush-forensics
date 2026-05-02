# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Realm viewer — header, schema, top-ref comparison, hex preview."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from crush.viewers.tree_viewer import TreeViewer
from crush.viewers.hex_viewer import HexViewer
from crush.viewers.table_viewer import TableViewer


def _create_realm_sqlite(table_data: dict[str, Any]) -> Path | None:
    """Dump decoded Realm tables into a temporary SQLite file.

    Each table gets a leading _objkey column holding the Realm ObjKey so that
    link columns from other tables can be JOINed:
        SELECT * FROM class_Article a
        JOIN class_ArticleEDP e ON a.edp = e._objkey

    Returns the Path to the temp file, or None on failure.
    The caller is responsible for cleanup (TableViewer.closeEvent handles it).
    """
    def _q(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    try:
        fd, path_str = tempfile.mkstemp(suffix=".db", prefix="crush_realm_")
        os.close(fd)
        conn = sqlite3.connect(path_str)
        for tbl_name, tbl in table_data.items():
            cols: list[str] = tbl.get("columns", [])
            rows: list[list] = tbl.get("rows", [])
            obj_keys: list = tbl.get("__obj_keys") or []
            if not cols:
                continue
            col_defs = "_objkey INTEGER, " + ", ".join(_q(c) for c in cols)
            conn.execute(f"CREATE TABLE {_q(tbl_name)} ({col_defs})")  # noqa: S608
            if rows:
                ph = ", ".join("?" * (len(cols) + 1))
                conn.executemany(
                    f"INSERT INTO {_q(tbl_name)} VALUES ({ph})",  # noqa: S608
                    [
                        [obj_keys[i] if i < len(obj_keys) else None] + row
                        for i, row in enumerate(rows)
                    ],
                )
        conn.commit()
        conn.close()
        return Path(path_str)
    except Exception:
        return None


class RealmViewer(QWidget):
    """Realm viewer with tabs: Header | Schema | Top Refs | Hex Preview."""

    def __init__(self, data: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data = data
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()

        tables: list[dict] = self._data.get("tables", [])

        # --- Header ---
        header = self._data.get("header")
        if header:
            tabs.addTab(TreeViewer({"Header": header}, tabs), "Header")
        else:
            lbl = QLabel("Header not detected (possibly encrypted or non-standard).")
            lbl.setWordWrap(True)
            tabs.addTab(lbl, "Header")

        # --- Schema ---
        schema: list[str] = self._data.get("schema", [])
        if schema:
            table_lookup: dict[str, dict] = {t.get("name", ""): t for t in tables}
            schema_tree: dict[str, Any] = {}
            for name in schema:
                t = table_lookup.get(name)
                if t:
                    col_names: list[str] = t.get("column_names") or []
                    col_types: list[str] = t.get("column_types") or []
                    n_rows = t.get("row_count")
                    rows_label = f"{n_rows} rows" if n_rows is not None else "? rows"
                    label = f"{name}  ({rows_label}, {len(col_names)} cols)"
                    schema_tree[label] = {
                        col_names[i]: col_types[i] if i < len(col_types) else "?"
                        for i in range(len(col_names))
                    }
                else:
                    schema_tree[name] = "(no column data decoded)"
            tabs.addTab(
                TreeViewer({f"Tables ({len(schema)})": schema_tree}, tabs), "Schema"
            )

        # --- Top Refs ---
        top_refs = self._data.get("top_refs", {})
        if top_refs:
            tabs.addTab(self._build_top_refs_tab(top_refs, tabs), "Top Refs")

        # --- Tables ---
        if tables:
            tabs.addTab(self._build_tables_tab(tables, tabs), "Tables")

        # --- Strings ---
        strings: list[str] = self._data.get("strings", [])
        if strings:
            strings_data: dict[str, Any] = {
                f"Strings ({len(strings)})": {
                    "columns": ["String"],
                    "rows": [[s] for s in strings],
                }
            }
            tabs.addTab(TableViewer(strings_data, tabs), "Strings")

        # --- Hex Preview ---
        preview = self._data.get("preview", b"")
        tabs.addTab(HexViewer(preview, tabs), "Hex Preview")

        layout.addWidget(tabs)

    def _build_tables_tab(
        self, tables: list[dict], parent: QWidget
    ) -> QWidget:
        """Convert Realm table dicts to the TableViewer format and return the widget."""
        table_data: dict[str, Any] = {}
        summary_rows: list[list] = []

        for t in tables:
            name: str = t.get("name") or "?"
            cols_dict: dict[int, list] = t.get("columns", {})
            if not cols_dict:
                continue
            col_indices = sorted(cols_dict.keys())
            col_names = t.get("column_names")
            if col_names:
                col_headers = [
                    col_names[i] if i < len(col_names) else f"col_{i}"
                    for i in col_indices
                ]
            else:
                col_headers = [f"col_{i}" for i in col_indices]
            row_count = max((len(v) for v in cols_dict.values()), default=0)
            rows: list[list] = []
            for r in range(row_count):
                row = []
                for ci in col_indices:
                    vals = cols_dict[ci]
                    row.append(vals[r] if r < len(vals) else None)
                rows.append(row)
            obj_keys = t.get("obj_keys") or []
            table_data[name] = {
                "columns": col_headers,
                "rows": rows,
                "__obj_keys": obj_keys,
            }
            summary_rows.append([name, len(col_indices), row_count])

        viewer_data: dict[str, Any] = {
            "Summary": {
                "columns": ["Table", "Decoded cols", "Rows"],
                "rows": summary_rows,
            }
        }
        viewer_data.update(table_data)
        tmp = _create_realm_sqlite(table_data)
        if tmp:
            viewer_data["__db_path"] = str(tmp)
        return TableViewer(viewer_data, parent, show_db_tabs=False)

    def _build_top_refs_tab(
        self, top_refs: dict[str, Any], parent: QWidget
    ) -> QWidget:
        active_idx = top_refs.get("active_index", -1)
        tree: dict[str, Any] = {}

        for key, idx in (("top_ref_0", 0), ("top_ref_1", 1)):
            entry = top_refs.get(key, {})
            offset = entry.get("offset", 0)
            status = "ACTIVE" if idx == active_idx else "inactive"
            label = f"top_ref[{idx}] — {status}"
            hdr = entry.get("array_header")
            node_info: dict[str, Any] = {"File offset": f"0x{offset:x} ({offset})"}
            if hdr:
                node_info.update({k: str(v) for k, v in hdr.items()})
            else:
                node_info["Note"] = (
                    "Array header not readable (outside preview range or invalid)"
                )

            children = entry.get("children", [])
            if children:
                children_dict: dict[str, Any] = {}
                for child in children:
                    i = child["index"]
                    child_off = child["offset"]
                    child_hdr = child.get("array_header")
                    if child_hdr:
                        children_dict[f"[{i}] 0x{child_off:x}"] = {
                            "has_refs": str(child_hdr["has_refs"]),
                            "Element count": str(child_hdr["Element count (size)"]),
                            "width": str(child_hdr["width"]),
                            "width_scheme": str(child_hdr["width_scheme"]),
                            "Total bytes": str(child_hdr["Total array bytes"]),
                        }
                    else:
                        children_dict[f"[{i}]"] = (
                            f"0x{child_off:x} ({child_off}) — offset out of range"
                        )
                node_info["Children"] = children_dict

            tree[label] = node_info

        # Diff summary
        hdr0 = top_refs.get("top_ref_0", {}).get("array_header")
        hdr1 = top_refs.get("top_ref_1", {}).get("array_header")
        if hdr0 and hdr1:
            diff: dict[str, str] = {
                k: f"ref[0]={hdr0[k]}  vs  ref[1]={hdr1[k]}"
                for k in hdr0
                if str(hdr0[k]) != str(hdr1[k])
            }
            tree["Diff (changed fields)"] = (
                diff if diff else {"(none)": "Both top_refs are identical"}
            )

        return TreeViewer(tree, parent)
