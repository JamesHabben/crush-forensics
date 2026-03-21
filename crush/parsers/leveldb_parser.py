# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""LevelDB parser (vendored ccl_leveldb, MIT)."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import AbstractParser, ParseResult
from crush.third_party.ccl_leveldb import RawLevelDb

_DATA_FILE_RE = re.compile(r"^[0-9]{6}\\.(ldb|log|sst)$", re.IGNORECASE)


class LeveldbParser(AbstractParser):
    SUPPORTED_EXTENSIONS: list[str] = []
    DISPLAY_NAME = "LevelDB"

    def can_parse(self, path: str, peek_bytes: bytes) -> bool:  # noqa: ARG002
        # LevelDB is typically a directory; sniff via child filenames.
        return False

    def can_parse_dir(self, node: VFSNode) -> bool:
        for child in node.children:
            if _DATA_FILE_RE.match(child.name):
                return True
            if child.name.startswith("MANIFEST-"):
                return True
        return False

    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        if not node.is_dir:
            raise ValueError("LevelDB parser expects a directory")

        if not self.can_parse_dir(node):
            raise ValueError("Not a LevelDB directory")

        tmp_dir = Path(tempfile.mkdtemp(prefix="crush-leveldb-"))
        _export_dir(node, vfs, tmp_dir)

        max_records = 2000
        rows: list[list[Any]] = []
        total = 0
        with RawLevelDb(tmp_dir) as db:
            for record in db.iterate_records_raw():
                total += 1
                if len(rows) >= max_records:
                    continue
                rows.append(
                    [
                        record.seq,
                        record.state.name,
                        record.file_type.name,
                        Path(record.origin_file).name,
                        record.offset,
                        record.was_compressed,
                        record.user_key,
                        record.key,
                        record.value,
                    ]
                )

        data = {
            "LevelDB Records": {
                "columns": [
                    "Seq",
                    "State",
                    "File Type",
                    "Origin File",
                    "Offset",
                    "Compressed",
                    "User Key (BLOB)",
                    "Key (BLOB)",
                    "Value (BLOB)",
                ],
                "rows": rows,
            }
        }

        meta: dict[str, Any] = {
            "Format": "LevelDB",
            "Records": f"{total:,}",
            "Displayed": f"{len(rows):,}",
            "Files": f"{vfs.file_count(node):,}",
            "Total size": f"{vfs.total_size(node):,} B",
        }
        if total > len(rows):
            meta["Note"] = f"Showing first {len(rows):,} records"
        return ParseResult(viewer_type="table", data=data, metadata=meta)


def _export_dir(node: VFSNode, vfs: VFS, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in node.children:
        child_target = target / child.name
        if child.is_dir:
            _export_dir(child, vfs, child_target)
        else:
            child_target.parent.mkdir(parents=True, exist_ok=True)
            with vfs.open(child) as src, open(child_target, "wb") as dst:
                dst.write(src.read())
