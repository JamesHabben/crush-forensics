# SPDX-License-Identifier: Apache-2.0
"""Tests for SQLite in-page freeblock carving."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from crush.core.sqlite_freeblocks import extract_freeblocks, scan_database_freeblocks

_PAGE_SIZE = 1024


def _make_single_delete_db(path: Path) -> None:
    """Insert 10 rows, delete one from the middle.

    A single-row DELETE does not free the whole page (freelist_count stays
    0) — SQLite splices the cell into the page's freeblock list instead.
    """
    conn = sqlite3.connect(str(path))
    conn.execute(f"PRAGMA page_size={_PAGE_SIZE}")
    conn.execute("PRAGMA secure_delete=OFF")
    conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, body TEXT)")
    for i in range(10):
        conn.execute(
            "INSERT INTO messages (body) VALUES (?)", (f"row-{i}-payload-CANARY{i:02d}",)
        )
    conn.commit()
    conn.execute("DELETE FROM messages WHERE id = 5")
    conn.commit()
    conn.close()


def test_scan_database_freeblocks_recovers_deleted_row(tmp_path: Path) -> None:
    db_path = tmp_path / "single_delete.db"
    _make_single_delete_db(db_path)

    conn = sqlite3.connect(str(db_path))
    assert conn.execute("PRAGMA freelist_count").fetchone()[0] == 0
    conn.close()

    freeblocks = scan_database_freeblocks(db_path, _PAGE_SIZE)

    assert freeblocks
    assert any(b"CANARY04" in fb["data"] for fb in freeblocks)


def test_scan_database_freeblocks_empty_db_returns_nothing(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    conn.close()

    assert scan_database_freeblocks(db_path, page_size) == []


def test_extract_freeblocks_ignores_non_leaf_pages() -> None:
    # A page claiming to be a table-interior page (type 0x05) must be skipped
    # even if it happens to carry bytes that look like a freeblock pointer.
    page = bytearray(_PAGE_SIZE)
    page[0] = 0x05
    page[1:3] = (50).to_bytes(2, "big")
    assert extract_freeblocks(bytes(page)) == []


def test_extract_freeblocks_stops_on_cyclic_chain() -> None:
    # A freeblock whose "next" pointer points back at itself must not hang.
    page = bytearray(_PAGE_SIZE)
    page[0] = 0x0D  # table-leaf
    page[1:3] = (16).to_bytes(2, "big")  # first freeblock at offset 16
    page[16:18] = (16).to_bytes(2, "big")  # next -> itself (cycle)
    page[18:20] = (8).to_bytes(2, "big")  # size 8
    freeblocks = extract_freeblocks(bytes(page))
    assert len(freeblocks) == 1
