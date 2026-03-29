# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""FormatDatabase — runtime wrapper around the bundled formats.db knowledge base."""
from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path


def _resolve_db_path() -> Path:
    # PyInstaller extracts data files to sys._MEIPASS when frozen
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent.parent
    return base / "data" / "formats.db"


_DB_PATH = _resolve_db_path()


@dataclass
class FormatMatch:
    name: str
    short_name: str
    category: str
    forensic_relevance: str
    platforms: str
    parser_class: str | None   # e.g. "SQLiteParser", or None if unsupported
    links: list[tuple[str, str]]  # [(label, url), ...]
    magic: list[tuple[int | None, bytes, str]]  # [(offset, pattern, description), ...]


class FormatDatabase:
    """Singleton read-only wrapper around formats.db."""

    _instance: FormatDatabase | None = None

    @classmethod
    def get(cls) -> FormatDatabase:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._conn: sqlite3.Connection | None = None
        if not _DB_PATH.exists():
            return
        try:
            self._conn = sqlite3.connect(
                f"file:{_DB_PATH}?mode=ro", uri=True, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
        except Exception:
            self._conn = None

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def identify(self, peek_bytes: bytes, filename: str) -> FormatMatch | None:
        """Return the best format match by magic bytes, or None."""
        if self._conn is None:
            return None

        # 1. Magic bytes — fetch all patterns and test in Python
        #    (avoids SQL BLOB comparison portability issues)
        cur = self._conn.execute(
            "SELECT f.*, m.offset, m.pattern "
            "FROM formats f JOIN magic_bytes m ON m.format_id = f.id"
        )
        for row in cur:
            offset = row["offset"]
            if offset is None:
                continue
            pattern: bytes = row["pattern"]
            end = offset + len(pattern)
            if len(peek_bytes) >= end and peek_bytes[offset:end] == pattern:
                return self._row_to_match(row)

        return None

    def by_parser_class(self, class_name: str) -> FormatMatch | None:
        """Look up format metadata for a parser that successfully handled a file."""
        if self._conn is None:
            return None
        row = self._conn.execute(
            "SELECT * FROM formats WHERE parser_class = ? LIMIT 1",
            (class_name,),
        ).fetchone()
        return self._row_to_match(row) if row else None

    def all_formats(self) -> list[FormatMatch]:
        """Return all known formats ordered by category then name."""
        if self._conn is None:
            return []
        return [
            self._row_to_match(r)
            for r in self._conn.execute(
                "SELECT * FROM formats ORDER BY category, name"
            )
        ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _row_to_match(self, row: sqlite3.Row) -> FormatMatch:
        fid = row["id"]
        links: list[tuple[str, str]] = []
        if self._conn:
            links = [
                (r["label"], r["url"])
                for r in self._conn.execute(
                    "SELECT label, url FROM links WHERE format_id = ? ORDER BY id",
                    (fid,),
                )
            ]
        magic: list[tuple[int, bytes, str]] = []
        if self._conn:
            magic = [
                (r["offset"], r["pattern"], r["description"] or "")
                for r in self._conn.execute(
                    "SELECT offset, pattern, description FROM magic_bytes "
                    "WHERE format_id = ? ORDER BY id",
                    (fid,),
                )
            ]
        return FormatMatch(
            name=row["name"],
            short_name=row["short_name"] or "",
            category=row["category"] or "",
            forensic_relevance=row["forensic_relevance"] or "",
            platforms=row["platforms"] or "",
            parser_class=row["parser_class"],
            links=links,
            magic=magic,
        )
