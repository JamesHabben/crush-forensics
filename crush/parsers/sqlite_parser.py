"""SQLite parser — reads tables, columns, and row data."""
from __future__ import annotations

import sqlite3
import tempfile
from typing import Any

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import AbstractParser, ParseResult

# SQLite magic bytes
_SQLITE_MAGIC = b"SQLite format 3\x00"


class SQLiteParser(AbstractParser):
    SUPPORTED_EXTENSIONS = [".db", ".sqlite", ".sqlite3", ".db3"]
    DISPLAY_NAME = "SQLite database"

    def can_parse(self, path: str, peek_bytes: bytes) -> bool:
        return peek_bytes[:16] == _SQLITE_MAGIC

    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        raw = vfs.read(node)

        # Write to a temp file so sqlite3 can open it
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name

        try:
            conn = sqlite3.connect(tmp_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Enumerate tables
            tables = [
                r[0]
                for r in cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            ]

            # Build structured data: {table_name: {columns: [...], rows: [...]}}
            data: dict[str, Any] = {"__db_path": tmp_path}
            text_parts: list[str] = []

            for table in tables:
                cursor.execute(f"SELECT * FROM [{table}] LIMIT 500")  # noqa: S608
                rows = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description or []]
                data[table] = {
                    "columns": columns,
                    "rows": [list(row) for row in rows],
                }
                # Index text columns for search
                for row in rows:
                    for val in row:
                        if isinstance(val, str) and val.strip():
                            text_parts.append(val)

            # Metadata
            pragma_rows = cursor.execute("PRAGMA page_size").fetchone()
            page_size = pragma_rows[0] if pragma_rows else "?"
            wal = cursor.execute("PRAGMA journal_mode").fetchone()
            encoding = cursor.execute("PRAGMA encoding").fetchone()

            meta = {
                "Tables": str(len(tables)),
                "Page size": f"{page_size} B",
                "Journal mode": wal[0] if wal else "?",
                "Encoding": encoding[0] if encoding else "?",
                "File size": f"{node.size:,} B",
            }

            conn.close()
        finally:
            pass

        return ParseResult(
            viewer_type="table",
            data=data,
            metadata=meta,
            text_index=" ".join(text_parts[:2000]),
        )
