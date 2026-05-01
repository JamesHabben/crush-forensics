# SPDX-License-Identifier: Apache-2.0
"""SQLite WAL page parser and B-tree attribution utilities.

Implements:
  - SQLite varint decoder
  - Record-format row extractor (serial-type decoder, no overflow chasing)
  - Table-leaf page parser (page type 0x0D)
  - Page→table attribution map built by walking B-tree interior pages
"""
from __future__ import annotations

import sqlite3
import struct
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Varint
# ---------------------------------------------------------------------------

def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Return (value, bytes_consumed) for the SQLite varint at *offset*."""
    result = 0
    for i in range(9):
        byte = data[offset + i]
        if i < 8:
            result = (result << 7) | (byte & 0x7F)
            if not (byte & 0x80):
                return result, i + 1
        else:
            # 9th byte: all 8 bits contribute
            result = (result << 8) | byte
            return result, 9
    return result, 9  # unreachable but satisfies type checker


# ---------------------------------------------------------------------------
# Record format
# ---------------------------------------------------------------------------

_NULL    = object()  # sentinel for NULL cells


def _decode_record(payload: bytes) -> list[Any]:
    """Decode a SQLite record payload into a list of Python values.

    Overflow payloads are not followed — values that would require an
    overflow page are returned as the sentinel string '<OVERFLOW>'.
    """
    if not payload:
        return []

    hdr_size, consumed = _read_varint(payload, 0)
    pos = consumed
    serial_types: list[int] = []
    while pos < hdr_size:
        stype, n = _read_varint(payload, pos)
        serial_types.append(stype)
        pos += n

    values: list[Any] = []
    body_pos = hdr_size
    for stype in serial_types:
        if stype == 0:
            values.append(None)
        elif stype == 1:
            if body_pos + 1 > len(payload):
                values.append("<TRUNCATED>")
            else:
                values.append(struct.unpack_from(">b", payload, body_pos)[0])
            body_pos += 1
        elif stype == 2:
            if body_pos + 2 > len(payload):
                values.append("<TRUNCATED>")
            else:
                values.append(struct.unpack_from(">h", payload, body_pos)[0])
            body_pos += 2
        elif stype == 3:
            if body_pos + 3 > len(payload):
                values.append("<TRUNCATED>")
            else:
                raw = payload[body_pos:body_pos + 3]
                v = int.from_bytes(raw, "big", signed=True)
                values.append(v)
            body_pos += 3
        elif stype == 4:
            if body_pos + 4 > len(payload):
                values.append("<TRUNCATED>")
            else:
                values.append(struct.unpack_from(">i", payload, body_pos)[0])
            body_pos += 4
        elif stype == 5:
            if body_pos + 6 > len(payload):
                values.append("<TRUNCATED>")
            else:
                raw = payload[body_pos:body_pos + 6]
                v = int.from_bytes(raw, "big", signed=True)
                values.append(v)
            body_pos += 6
        elif stype == 6:
            if body_pos + 8 > len(payload):
                values.append("<TRUNCATED>")
            else:
                values.append(struct.unpack_from(">q", payload, body_pos)[0])
            body_pos += 8
        elif stype == 7:
            if body_pos + 8 > len(payload):
                values.append("<TRUNCATED>")
            else:
                values.append(struct.unpack_from(">d", payload, body_pos)[0])
            body_pos += 8
        elif stype == 8:
            values.append(0)
        elif stype == 9:
            values.append(1)
        elif stype >= 12 and stype % 2 == 0:
            length = (stype - 12) // 2
            if length == 0:
                values.append(b"")
            elif body_pos + length > len(payload):
                values.append("<OVERFLOW>")
            else:
                values.append(bytes(payload[body_pos:body_pos + length]))
            body_pos += length
        elif stype >= 13 and stype % 2 == 1:
            length = (stype - 13) // 2
            if length == 0:
                values.append("")
            elif body_pos + length > len(payload):
                values.append("<OVERFLOW>")
            else:
                try:
                    values.append(payload[body_pos:body_pos + length].decode("utf-8", errors="replace"))
                except Exception:
                    values.append(bytes(payload[body_pos:body_pos + length]))
            body_pos += length
        else:
            values.append(None)  # reserved serial types 10, 11

    return values


# ---------------------------------------------------------------------------
# Table leaf page parser
# ---------------------------------------------------------------------------

PAGE_TYPE_TABLE_LEAF     = 0x0D
PAGE_TYPE_TABLE_INTERIOR = 0x05
PAGE_TYPE_INDEX_LEAF     = 0x0A
PAGE_TYPE_INDEX_INTERIOR = 0x02


def parse_table_leaf_page(page: bytes) -> list[tuple[int, list[Any]]] | None:
    """Parse a SQLite table-leaf page (type 0x0D).

    Returns a list of (rowid, [values]) tuples, or None if the page is not a
    table-leaf page or is corrupt.  Overflow content is returned as the
    string '<OVERFLOW>' — overflow pages are not followed.
    """
    if len(page) < 8:
        return None
    page_type = page[0]
    if page_type != PAGE_TYPE_TABLE_LEAF:
        return None

    # cell_count at offset 3 (2 bytes)
    cell_count = struct.unpack_from(">H", page, 3)[0]
    if cell_count == 0:
        return []

    # Cell pointer array starts at offset 8 (table-leaf has no rightmost-pointer)
    ptr_area_start = 8
    rows: list[tuple[int, list[Any]]] = []

    for i in range(cell_count):
        ptr_off = ptr_area_start + i * 2
        if ptr_off + 2 > len(page):
            break
        cell_offset = struct.unpack_from(">H", page, ptr_off)[0]
        if cell_offset == 0 or cell_offset >= len(page):
            continue
        try:
            pos = cell_offset
            payload_size, n = _read_varint(page, pos)
            pos += n
            rowid, n = _read_varint(page, pos)
            pos += n
            # Inline payload: min(payload_size, max_inline)
            # For leaf pages, max inline = page_size - 35; we just take what's there.
            inline = min(payload_size, len(page) - pos)
            payload = bytes(page[pos:pos + inline])
            values = _decode_record(payload)
            rows.append((rowid, values))
        except Exception:
            continue

    return rows


def get_page_type(page: bytes) -> int | None:
    """Return the page-type byte, or None if the page is too short."""
    return page[0] if page else None


# ---------------------------------------------------------------------------
# Page → table attribution
# ---------------------------------------------------------------------------

def build_page_table_map(
    conn: sqlite3.Connection,
    wal_data: bytes | None = None,
    page_size: int = 0,
) -> dict[int, str]:
    """Return a mapping of {page_number: table_name} for every page reachable
    from a table's B-tree root.

    Works by reading sqlite_master root pages, then walking interior pages
    (from the DB connection or from WAL frames) to collect all child page
    numbers.  Index pages and non-table objects are excluded.
    """
    mapping: dict[int, str] = {}

    # Build WAL frame lookup: page_num → latest page bytes (active frames only)
    wal_pages: dict[int, bytes] = {}
    if wal_data and page_size:
        if len(wal_data) >= 32:
            magic = struct.unpack_from(">I", wal_data, 0)[0]
            if magic in (0x377F0682, 0x377F0683):
                salt1 = struct.unpack_from(">I", wal_data, 16)[0]
                salt2 = struct.unpack_from(">I", wal_data, 20)[0]
                frame_size = 24 + page_size
                offset = 32
                # Collect last valid frame per page (active)
                while offset + frame_size <= len(wal_data):
                    pn    = struct.unpack_from(">I", wal_data, offset)[0]
                    fs1   = struct.unpack_from(">I", wal_data, offset + 8)[0]
                    fs2   = struct.unpack_from(">I", wal_data, offset + 12)[0]
                    if fs1 == salt1 and fs2 == salt2:
                        wal_pages[pn] = wal_data[offset + 24: offset + 24 + page_size]
                    offset += frame_size

    # Read sqlite_master for table root pages and schemas
    try:
        rows = conn.execute(
            "SELECT name, rootpage FROM sqlite_master WHERE type='table'"
        ).fetchall()
    except Exception:
        return mapping

    # For each root page, BFS-walk interior pages to collect all child pages
    for name, rootpage in rows:
        if rootpage is None:
            continue
        mapping[rootpage] = name
        _walk_interior(rootpage, name, mapping, conn, wal_pages, page_size, set())

    return mapping


def _walk_interior(
    page_num: int,
    table_name: str,
    mapping: dict[int, str],
    conn: sqlite3.Connection,
    wal_pages: dict[int, bytes],
    page_size: int,
    visited: set[int],
) -> None:
    """Recursively collect all child pages of *page_num* into *mapping*."""
    if page_num in visited:
        return
    visited.add(page_num)

    page = _read_page(page_num, conn, wal_pages, page_size)
    if page is None or len(page) < 1:
        return
    page_type = page[0]
    if page_type not in (PAGE_TYPE_TABLE_INTERIOR, PAGE_TYPE_TABLE_LEAF):
        return
    if page_type != PAGE_TYPE_TABLE_INTERIOR:
        return  # leaf — no children to walk

    # Interior page header: type(1) + freeblock(2) + cell_count(2) +
    #                       content_start(2) + fragmented(1) + rightmost(4) = 12
    if len(page) < 12:
        return
    cell_count = struct.unpack_from(">H", page, 3)[0]
    rightmost  = struct.unpack_from(">I", page, 8)[0]
    mapping[rightmost] = table_name
    _walk_interior(rightmost, table_name, mapping, conn, wal_pages, page_size, visited)

    ptr_area_start = 12
    for i in range(cell_count):
        ptr_off = ptr_area_start + i * 2
        if ptr_off + 2 > len(page):
            break
        cell_offset = struct.unpack_from(">H", page, ptr_off)[0]
        if cell_offset + 4 > len(page):
            continue
        child_page = struct.unpack_from(">I", page, cell_offset)[0]
        if child_page and child_page not in mapping:
            mapping[child_page] = table_name
            _walk_interior(child_page, table_name, mapping, conn, wal_pages, page_size, visited)


def _read_page(
    page_num: int,
    conn: sqlite3.Connection,
    wal_pages: dict[int, bytes],
    page_size: int,
) -> bytes | None:
    """Return raw page bytes for *page_num*, preferring WAL over DB file."""
    if page_num in wal_pages:
        return wal_pages[page_num]
    # Read from DB file via the DBSTAT virtual table
    try:
        row = conn.execute(
            "SELECT pgno FROM dbstat WHERE pgno=? LIMIT 1", (page_num,)
        ).fetchone()
        if row is None:
            return None
        # Use sqlite3's undocumented raw page read — fall back to zeroed page
        # The safest cross-platform way: read the DB file directly
        db_path_row = conn.execute("PRAGMA database_list").fetchone()
        if db_path_row is None:
            return None
        db_path = Path(db_path_row[2])
        if not db_path.is_file() or page_size == 0:
            return None
        file_offset = (page_num - 1) * page_size
        with open(db_path, "rb") as fh:
            fh.seek(file_offset)
            data = fh.read(page_size)
        return data if len(data) == page_size else None
    except Exception:
        return None
