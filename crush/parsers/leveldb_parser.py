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

        import logging
        _logger = logging.getLogger(__name__)

        tmp_dir = Path(tempfile.mkdtemp(prefix="crush-leveldb-"))
        try:
            _export_dir(node, vfs, tmp_dir)

            max_records = 2000
            rows: list[list[Any]] = []
            total = 0
            parse_warning = ""

            try:
                with RawLevelDb(tmp_dir) as db:
                    for record in db.iterate_records_raw():
                        total += 1
                        if len(rows) >= max_records:
                            continue
                        try:
                            rows.append([
                                record.seq,
                                record.state.name,
                                record.file_type.name,
                                Path(record.origin_file).name,
                                record.offset,
                                record.was_compressed,
                                record.user_key,
                                record.key,
                                record.value,
                            ])
                        except Exception as exc:
                            parse_warning = f"Record {total} failed: {exc}"
                            _logger.debug("LevelDB record error: %s", exc)
            except Exception as exc:
                _logger.warning("LevelDB read error for %s: %s", node.path, exc)
                if not rows:
                    return ParseResult(
                        viewer_type="tree",
                        data={"error": str(exc), "hint": "LevelDB could not be opened"},
                        metadata={
                            "Format": "LevelDB (parse failed)",
                            "Parse error": str(exc),
                            "Files": f"{vfs.file_count(node):,}",
                        },
                    )
                parse_warning = str(exc)

            data = {
                "LevelDB Records": {
                    "columns": [
                        "Seq", "State", "File Type", "Origin File",
                        "Offset", "Compressed", "User Key (BLOB)", "Key (BLOB)", "Value (BLOB)",
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
            if parse_warning:
                meta["Parse warning"] = parse_warning
            return ParseResult(viewer_type="table", data=data, metadata=meta)

        finally:
            import shutil
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass


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
