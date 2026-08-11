# SPDX-License-Identifier: Apache-2.0
"""Tests for SQLite intra-page unallocated-space carving."""
from __future__ import annotations

import sqlite3
import struct
from pathlib import Path

from crush.core.sqlite_unallocated import (
    extract_unallocated_space,
    scan_database_unallocated,
)

_PAGE_SIZE = 1024


def _make_page(cell_count: int, content_start: int, gap_fill: bytes) -> bytes:
    page = bytearray(_PAGE_SIZE)
    page[0] = 0x0D  # table-leaf
    struct.pack_into(">H", page, 3, cell_count)
    struct.pack_into(">H", page, 5, content_start)
    ptr_array_end = 8 + cell_count * 2
    end = min(ptr_array_end + len(gap_fill), content_start)
    page[ptr_array_end:end] = gap_fill[: end - ptr_array_end]
    return bytes(page)


def test_extract_unallocated_space_returns_none_for_all_zero_gap() -> None:
    page = _make_page(cell_count=2, content_start=900, gap_fill=b"")
    assert extract_unallocated_space(page) is None


def test_extract_unallocated_space_returns_nonzero_gap() -> None:
    page = _make_page(cell_count=2, content_start=900, gap_fill=b"leftover-bytes")
    entry = extract_unallocated_space(page)
    assert entry is not None
    assert entry["offset"] == 12  # 8 + 2*2
    assert entry["data"].startswith(b"leftover-bytes")


def test_extract_unallocated_space_ignores_non_leaf_pages() -> None:
    page = bytearray(_make_page(cell_count=2, content_start=900, gap_fill=b"data"))
    page[0] = 0x05  # table-interior
    assert extract_unallocated_space(bytes(page)) is None


def test_scan_database_unallocated_after_real_page_compaction(tmp_path: Path) -> None:
    """Force a real defragmentation (content_start actually moves) and confirm
    the scanner finds the resulting gap -- regardless of what ends up in it,
    since SQLite empirically doesn't guarantee recoverable text there."""
    db_path = tmp_path / "compact.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(f"PRAGMA page_size={_PAGE_SIZE}")
    conn.execute("PRAGMA secure_delete=OFF")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, body TEXT)")
    for i in range(20):
        conn.execute("INSERT INTO t (body) VALUES (?)", (f"CANARY{i:02d}-" + "x" * 20,))
    conn.commit()
    root = conn.execute("SELECT rootpage FROM sqlite_master WHERE name='t'").fetchone()[0]

    content_start_before = _read_content_start(db_path, root)

    conn.execute("DELETE FROM t WHERE id IN (2,5,8,11,14,17)")
    conn.commit()
    conn.execute("INSERT INTO t (body) VALUES (?)", ("BIGROW-" + "Q" * 150,))
    conn.commit()
    conn.close()

    content_start_after = _read_content_start(db_path, root)
    assert content_start_after != content_start_before, "test setup didn't force compaction"

    results = scan_database_unallocated(db_path, _PAGE_SIZE)
    assert any(r["page"] == root for r in results)


def _read_content_start(db_path: Path, page_num: int) -> int:
    with open(db_path, "rb") as fh:
        fh.seek((page_num - 1) * _PAGE_SIZE)
        page = fh.read(_PAGE_SIZE)
    raw = struct.unpack_from(">H", page, 5)[0]
    return raw if raw != 0 else 65536
