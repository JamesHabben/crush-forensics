# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Realm viewer — header, schema, top-ref comparison, hex preview."""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from crush.viewers.tree_viewer import TreeViewer
from crush.viewers.hex_viewer import HexViewer
from crush.viewers.table_viewer import TableViewer


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
            schema_dict: dict[str, Any] = {
                f"Tables ({len(schema)})": {
                    str(i): name for i, name in enumerate(schema)
                }
            }
            tabs.addTab(TreeViewer(schema_dict, tabs), "Schema")

        # --- Top Refs ---
        top_refs = self._data.get("top_refs", {})
        if top_refs:
            tabs.addTab(self._build_top_refs_tab(top_refs, tabs), "Top Refs")

        # --- Tables ---
        tables: list[dict] = self._data.get("tables", [])
        if tables:
            tabs.addTab(self._build_tables_tab(tables, tabs), "Tables")

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
            col_headers = [f"col_{i}" for i in col_indices]
            row_count = max((len(v) for v in cols_dict.values()), default=0)
            rows: list[list] = []
            for r in range(row_count):
                row = []
                for ci in col_indices:
                    vals = cols_dict[ci]
                    row.append(vals[r] if r < len(vals) else None)
                rows.append(row)
            table_data[name] = {"columns": col_headers, "rows": rows}
            summary_rows.append([name, len(col_indices), row_count])

        viewer_data: dict[str, Any] = {
            "Summary": {
                "columns": ["Table", "Decoded cols", "Rows"],
                "rows": summary_rows,
            }
        }
        viewer_data.update(table_data)
        return TableViewer(viewer_data, parent)

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
                node_info["Note"] = "Array header not readable (outside preview range or invalid)"

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
                            "Element count (size)": str(child_hdr["Element count (size)"]),
                            "width": str(child_hdr["width"]),
                            "width_scheme": str(child_hdr["width_scheme"]),
                            "Total array bytes": str(child_hdr["Total array bytes"]),
                        }
                    else:
                        children_dict[f"[{i}]"] = f"0x{child_off:x} ({child_off}) — offset out of range"
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
