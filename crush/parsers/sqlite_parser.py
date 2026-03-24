"""SQLite parser — reads tables, columns, and row data."""
from __future__ import annotations

import logging
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from crush.core.vfs import VFS, VFSNode, find_sibling
from crush.parsers.base import AbstractParser, ParseResult

_SQLITE_MAGIC = b"SQLite format 3\x00"
_ROW_LIMIT = 10_000
_logger = logging.getLogger(__name__)


class SQLiteParser(AbstractParser):
    SUPPORTED_EXTENSIONS = [".db", ".sqlite", ".sqlite3", ".db3"]
    DISPLAY_NAME = "SQLite database"

    def can_parse(self, path: str, peek_bytes: bytes) -> bool:
        return peek_bytes[:16] == _SQLITE_MAGIC

    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        raw = vfs.read(node)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name

        # Copy WAL and SHM companion files if present
        companions: list[str] = []
        for suffix in ("-wal", "-shm"):
            sibling = find_sibling(node, vfs, suffix)
            if sibling is not None:
                try:
                    sib_bytes = vfs.read(sibling)
                    sib_path = tmp_path + suffix
                    with open(sib_path, "wb") as f:
                        f.write(sib_bytes)
                    companions.append(sibling.name)
                    _logger.debug("Copied companion file: %s", sibling.name)
                except Exception as exc:
                    _logger.debug("Could not copy companion %s: %s", sibling.name, exc)

        try:
            conn = sqlite3.connect(tmp_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            tables = [
                r[0]
                for r in cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            ]

            data: dict[str, Any] = {"__db_path": tmp_path}
            text_parts: list[str] = []
            truncated_tables: list[str] = []

            for table in tables:
                try:
                    cursor.execute(f"SELECT * FROM [{table}] LIMIT {_ROW_LIMIT + 1}")  # noqa: S608
                    raw_rows = cursor.fetchall()
                    was_truncated = len(raw_rows) > _ROW_LIMIT
                    rows = [list(r) for r in raw_rows[:_ROW_LIMIT]]
                    columns = [desc[0] for desc in cursor.description or []]
                    data[table] = {
                        "columns": columns,
                        "rows": rows,
                        "truncated": was_truncated,
                    }
                    if was_truncated:
                        truncated_tables.append(table)
                    for row in rows:
                        for val in row:
                            if isinstance(val, str) and val.strip():
                                text_parts.append(val)
                except Exception as exc:
                    _logger.warning("Error reading table %r: %s", table, exc)
                    data[table] = {
                        "columns": ["(error)"],
                        "rows": [[str(exc)]],
                        "truncated": False,
                    }

            try:
                pragma_rows = cursor.execute("PRAGMA page_size").fetchone()
                page_size = pragma_rows[0] if pragma_rows else "?"
                wal = cursor.execute("PRAGMA journal_mode").fetchone()
                encoding = cursor.execute("PRAGMA encoding").fetchone()
            except Exception:
                page_size, wal, encoding = "?", None, None

            meta: dict[str, Any] = {
                "Tables": str(len(tables)),
                "Page size": f"{page_size} B",
                "Journal mode": wal[0] if wal else "?",
                "Encoding": encoding[0] if encoding else "?",
                "File size": f"{node.size:,} B",
            }
            if companions:
                meta["Companion files"] = ", ".join(companions)
            if truncated_tables:
                meta["Row limit"] = f"First {_ROW_LIMIT:,} rows shown for: {', '.join(truncated_tables)}"

            conn.close()
        except Exception as exc:
            _logger.warning("SQLite parse error for %s: %s", node.path, exc)
            return ParseResult(
                viewer_type="hex",
                data=raw,
                metadata={
                    "Parse error": str(exc),
                    "Format": "SQLite (parse failed)",
                    "File size": f"{node.size:,} B",
                },
            )

        return ParseResult(
            viewer_type="table",
            data=data,
            metadata=meta,
            text_index=" ".join(text_parts[:2000]),
        )
