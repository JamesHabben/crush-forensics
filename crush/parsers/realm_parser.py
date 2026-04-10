# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Realm database parser — header + array structure decoding."""
from __future__ import annotations

import re
from typing import Any

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import AbstractParser, ParseResult

_HEADER_SIZE = 24
_MNEMONIC = b"T-DB"

# width_ndx (bits [2:0] of array flags byte) → element width value
# Scheme 0: width is in bits.  Scheme 1: width is in bytes.
_WIDTH_TABLE = [0, 1, 2, 4, 8, 16, 32, 64]


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _read_at(vfs: VFS, node: VFSNode, offset: int, size: int) -> bytes:
    if offset < 0:
        return b""
    try:
        with vfs.open(node) as src:
            try:
                src.seek(offset)
                return src.read(size)
            except Exception:
                data = src.read()
        return data[offset : offset + size]
    except Exception:
        return b""


# ---------------------------------------------------------------------------
# File header (24 bytes)
# ---------------------------------------------------------------------------

def _parse_realm_header(data: bytes) -> dict[str, Any] | None:
    if len(data) < _HEADER_SIZE:
        return None

    mnemonic = data[16:20]
    if mnemonic != _MNEMONIC:
        return None

    top_ref0 = int.from_bytes(data[0:8], "little")
    top_ref1 = int.from_bytes(data[8:16], "little")
    fmt0 = data[20]
    fmt1 = data[21]
    reserved = data[22]
    flags = data[23]
    active = 1 if (flags & 0x01) else 0

    return {
        "Top reference 0": f"{top_ref0} (0x{top_ref0:x})",
        "Top reference 1": f"{top_ref1} (0x{top_ref1:x})",
        "Mnemonic": mnemonic.decode("ascii", errors="replace"),
        "File format (top ref 0)": fmt0,
        "File format (top ref 1)": fmt1,
        "Reserved": reserved,
        "Flags": f"0x{flags:02x}",
        "Active top reference": active,
    }


# ---------------------------------------------------------------------------
# Array header (8 bytes) — see TODO.md §3 for the full spec
# ---------------------------------------------------------------------------

def _parse_array_header(data: bytes, offset: int = 0) -> dict[str, Any] | None:
    """Parse a Realm 8-byte array header at *offset* inside *data*.

    Array header layout:
        [0:4]  checksum   — always 0x41414141 ("AAAA")
        [4]    flags      — 5 bit-groups (see below)
        [5:8]  size       — big-endian uint24: number of elements in payload

    Flags byte (MSB = bit 7):
        bit 7       is_inner_bptree_node
        bit 6       has_refs  (1 = Reference Array; payload = file offsets)
        bit 5       context_flag  (purpose unclear)
        bits [4:3]  width_scheme  (0=bits, 1=bytes, 2=size-only)
        bits [2:0]  width_ndx  → _WIDTH_TABLE lookup

    Payload size formulas (before 8-byte alignment):
        scheme 0:  ceil(width_bits * size / 8)
        scheme 1:  width_bytes * size
        scheme 2:  size
    """
    if offset < 0 or len(data) < offset + 8:
        return None
    chunk = data[offset : offset + 8]
    if chunk[0:4] != b"\x41\x41\x41\x41":
        return None

    flags = chunk[4]
    size = int.from_bytes(chunk[5:8], "big")

    is_inner = bool((flags >> 7) & 1)
    has_refs = bool((flags >> 6) & 1)
    context_flag = bool((flags >> 5) & 1)
    width_scheme = (flags >> 3) & 3
    width_ndx = flags & 7
    width = _WIDTH_TABLE[width_ndx]

    if width_scheme == 0:
        payload_bytes = (width * size + 7) // 8 if width > 0 else 0
    elif width_scheme == 1:
        payload_bytes = width * size
    else:
        payload_bytes = size

    payload_bytes_aligned = (payload_bytes + 7) & ~7

    return {
        "Checksum": "AAAA (0x41414141)",
        "Flags (raw)": f"0x{flags:02x} (0b{flags:08b})",
        "is_inner_bptree_node": is_inner,
        "has_refs": has_refs,
        "context_flag": context_flag,
        "width_scheme": width_scheme,
        "width_ndx": width_ndx,
        "width": width,
        "Element count (size)": size,
        "Payload bytes (raw)": payload_bytes,
        "Payload bytes (aligned)": payload_bytes_aligned,
        "Total array bytes": 8 + payload_bytes_aligned,
    }


def _elem_bytes(arr_hdr: dict[str, Any]) -> int:
    """Return element size in bytes for an already-decoded array header."""
    scheme = arr_hdr["width_scheme"]
    width = arr_hdr["width"]
    if scheme == 0:
        return width // 8 if width >= 8 else 0
    if scheme == 1:
        return int(width)
    return 0  # scheme 2: variable / size-only


def _read_ref(data: bytes, payload_start: int, index: int, elem_bytes: int) -> int:
    """Read one little-endian integer from an array payload at *index*."""
    off = payload_start + index * elem_bytes
    if elem_bytes < 1 or off + elem_bytes > len(data):
        return -1
    return int.from_bytes(data[off : off + elem_bytes], "little")


# ---------------------------------------------------------------------------
# Schema extraction
# ---------------------------------------------------------------------------

def _extract_root_children(
    data: bytes, root_offset: int, file_size: int
) -> list[dict[str, Any]]:
    """Return the child entries of a root Reference Array.

    For each of the N references stored in the root array, returns a dict with
    the child's file offset and its decoded array header (if readable).
    """
    root_hdr = _parse_array_header(data, root_offset)
    if root_hdr is None or not root_hdr["has_refs"]:
        return []

    ref_elem_bytes = _elem_bytes(root_hdr)
    if ref_elem_bytes < 1:
        return []

    size = root_hdr["Element count (size)"]
    payload_start = root_offset + 8
    children: list[dict[str, Any]] = []
    for i in range(size):
        offset = _read_ref(data, payload_start, i, ref_elem_bytes)
        child: dict[str, Any] = {"index": i, "offset": offset}
        if 0 < offset < file_size:
            child["array_header"] = _parse_array_header(data, offset)
        else:
            child["array_header"] = None
        children.append(child)
    return children


def _extract_schema(data: bytes, root_offset: int, file_size: int) -> list[str]:
    """Extract class/table names from the Realm schema group array.

    B+ tree path followed:
        root_offset  →  root Reference Array
        entry[0]     →  schema group Data Array
        each entry   →  null-terminated ASCII class name (padded to *width* bytes)
    """
    root_hdr = _parse_array_header(data, root_offset)
    if root_hdr is None or not root_hdr["has_refs"]:
        return []

    ref_elem_bytes = _elem_bytes(root_hdr)
    if ref_elem_bytes < 1:
        return []

    payload_start = root_offset + 8
    schema_offset = _read_ref(data, payload_start, 0, ref_elem_bytes)
    if schema_offset <= 0 or schema_offset >= file_size:
        return []

    schema_hdr = _parse_array_header(data, schema_offset)
    if schema_hdr is None:
        return []

    entry_bytes = _elem_bytes(schema_hdr)
    count = schema_hdr["Element count (size)"]
    if entry_bytes < 1 or count == 0:
        return []

    payload_start = schema_offset + 8
    names: list[str] = []
    for i in range(count):
        entry_off = payload_start + i * entry_bytes
        if entry_off + entry_bytes > len(data):
            break
        entry = data[entry_off : entry_off + entry_bytes]
        null_pos = entry.find(b"\x00")
        raw = entry[:null_pos] if null_pos >= 0 else entry
        try:
            name = raw.decode("ascii")
        except Exception:
            continue
        if name:
            names.append(name)

    return names


# ---------------------------------------------------------------------------
# Table data extraction
# ---------------------------------------------------------------------------

def _read_scalar_leaf(
    data: bytes,
    col_offset: int,
    file_size: int,
) -> list[int | bool | None] | None:
    """Parse a Realm scalar-column leaf node (integers or booleans).

    Handles simple Data Arrays (has_refs=0):
        width=1, scheme=0  → boolean (1 bit per row)
        width=2/4, scheme=0 → packed sub-byte unsigned integers
        width=8/16/32/64, scheme=0 or scheme=1 → little-endian unsigned integers

    Returns a list of values (``None`` where data is unreadable), or ``None``
    if the node does not look like a scalar leaf.
    """
    hdr = _parse_array_header(data, col_offset)
    if hdr is None or hdr["has_refs"]:
        return None

    count = hdr["Element count (size)"]
    width = hdr["width"]
    scheme = hdr["width_scheme"]
    payload_start = col_offset + 8

    if count == 0:
        return []

    if scheme == 0:
        if width == 0:
            return [0] * count
        payload = data[payload_start : payload_start + hdr["Payload bytes (raw)"]]
        if width == 1:
            result: list[int | bool | None] = []
            for i in range(count):
                byte_i, bit_i = divmod(i, 8)
                if byte_i < len(payload):
                    result.append(bool((payload[byte_i] >> bit_i) & 1))
                else:
                    result.append(None)
            return result
        if width in (2, 4, 8, 16, 32, 64):
            mask = (1 << width) - 1
            result = []
            for i in range(count):
                bit_pos = i * width
                byte_pos = bit_pos // 8
                bit_off = bit_pos % 8
                needed = (bit_off + width + 7) // 8
                if byte_pos + needed > len(payload):
                    result.append(None)
                    continue
                raw = 0
                for b in range(needed):
                    raw |= payload[byte_pos + b] << (b * 8)
                result.append((raw >> bit_off) & mask)
            return result

    elif scheme == 1:
        eb = int(width)
        if eb < 1:
            return None
        result = []
        for i in range(count):
            off = payload_start + i * eb
            if off + eb > len(data):
                result.append(None)
            else:
                result.append(int.from_bytes(data[off : off + eb], "little"))
        return result

    return None


def _read_string_leaf(
    data: bytes,
    col_offset: int,
    file_size: int,
    expected_rows: int | None = None,
) -> list[str | None] | None:
    """Parse a Realm string-column leaf node at *col_offset*.

    Realm stores string columns in a fixed 3-entry structure:
        col_offset → ref_array[3]
            [0] → offsets_array  (N × uint16, one byte-offset per row into the blob)
            [1] → blob_array     (scheme=2: raw string bytes, null-separated)
            [2] → null_bitmap    (1 bit per row; 1 = value is NULL)

    If *expected_rows* is given, the offsets array must have exactly that many
    entries (distinguishes string from blob columns, which have N+1 entries).

    Returns a list of N strings (``None`` where the row is NULL), or ``None``
    if the offset does not match the expected 3-entry pattern.
    """
    col_hdr = _parse_array_header(data, col_offset)
    if col_hdr is None or not col_hdr["has_refs"]:
        return None
    entry_count = col_hdr["Element count (size)"]
    # Accept both the modern 3-entry format [offsets, blob, null_bitmap] and the
    # legacy 2-entry format [offsets, blob] used before nullable string support.
    if entry_count not in (2, 3):
        return None

    eb = _elem_bytes(col_hdr)
    if eb < 1:
        return None

    offs_ref = _read_ref(data, col_offset + 8, 0, eb)
    blob_ref = _read_ref(data, col_offset + 8, 1, eb)
    null_ref = _read_ref(data, col_offset + 8, 2, eb) if entry_count == 3 else -1

    # Blob must be a scheme=2 (raw bytes) data array
    blob_hdr = _parse_array_header(data, blob_ref)
    if blob_hdr is None or blob_hdr["width_scheme"] != 2:
        return None
    blob_size = blob_hdr["Element count (size)"]
    blob = data[blob_ref + 8 : blob_ref + 8 + blob_size]

    # Offsets array: N elements, elem_bytes derived from its own header
    offs_hdr = _parse_array_header(data, offs_ref)
    if offs_hdr is None:
        return None
    row_count = offs_hdr["Element count (size)"]
    offs_eb = _elem_bytes(offs_hdr)
    if offs_eb < 1:
        return None

    # If the caller knows the expected row count, use it to reject blob columns
    # (blob offsets arrays have N+1 entries, string arrays have exactly N).
    if expected_rows is not None and row_count != expected_rows:
        return None

    # Null bitmap: 1 bit per row (width=1, scheme=0); absent in legacy 2-entry format
    null_bits: list[bool] = [False] * row_count
    if null_ref >= 0:
        null_hdr = _parse_array_header(data, null_ref)
        if null_hdr and not null_hdr["has_refs"] and null_hdr["width"] == 1:
            null_payload = data[null_ref + 8 : null_ref + 8 + null_hdr["Payload bytes (raw)"]]
            for i in range(row_count):
                byte_i, bit_i = divmod(i, 8)
                if byte_i < len(null_payload):
                    null_bits[i] = bool((null_payload[byte_i] >> bit_i) & 1)

    strings: list[str | None] = []
    for i in range(row_count):
        if null_bits[i]:
            strings.append(None)
            continue
        off = _read_ref(data, offs_ref + 8, i, offs_eb)
        if off < 0 or off >= len(blob):
            strings.append(None)
            continue
        null_pos = blob.find(b"\x00", off)
        end = null_pos if null_pos >= 0 else len(blob)
        try:
            strings.append(blob[off:end].decode("utf-8", errors="replace"))
        except Exception:
            strings.append(None)

    return strings


def _read_blob_leaf(
    data: bytes,
    col_offset: int,
    file_size: int,
    expected_rows: int | None = None,
) -> list[str | None] | None:
    """Parse a Realm binary/blob-column leaf node at *col_offset*.

    Blob columns use the same 3-entry ref-array structure as strings, but the
    offsets array has N+1 entries (cumulative byte offsets into the raw data
    block) rather than N per-string start offsets with null terminators.

        col_offset → ref_array[3]
            [0] → offsets_array  ((N+1) entries; end[i] = offsets[i+1])
            [1] → blob_array     (scheme=2: raw binary bytes)
            [2] → null_bitmap    (1 bit per row)

    If *expected_rows* is given, the offsets array must have exactly N+1
    entries to match the blob pattern; otherwise the column is skipped.

    Returns a list of N hex-string representations (``None`` where NULL), or
    ``None`` if the node does not match the expected blob pattern.
    """
    col_hdr = _parse_array_header(data, col_offset)
    if col_hdr is None or not col_hdr["has_refs"]:
        return None
    # Blob leaf uses a 3-entry structure [offsets(N+1), blob, null_bitmap].
    # A 2-entry form is not known for blob columns.
    if col_hdr["Element count (size)"] != 3:
        return None

    eb = _elem_bytes(col_hdr)
    if eb < 1:
        return None

    offs_ref = _read_ref(data, col_offset + 8, 0, eb)
    blob_ref = _read_ref(data, col_offset + 8, 1, eb)
    null_ref = _read_ref(data, col_offset + 8, 2, eb)

    blob_hdr = _parse_array_header(data, blob_ref)
    if blob_hdr is None or blob_hdr["width_scheme"] != 2:
        return None
    blob_size = blob_hdr["Element count (size)"]
    blob = data[blob_ref + 8 : blob_ref + 8 + blob_size]

    offs_hdr = _parse_array_header(data, offs_ref)
    if offs_hdr is None:
        return None
    offs_count = offs_hdr["Element count (size)"]
    offs_eb = _elem_bytes(offs_hdr)
    if offs_eb < 1 or offs_count < 1:
        return None

    # Blob columns: N rows → N+1 offset entries.
    # If expected_rows is known, enforce the distinction from string columns.
    if expected_rows is not None:
        if offs_count != expected_rows + 1:
            return None
        row_count = expected_rows
    else:
        row_count = offs_count - 1
    if row_count < 0:
        return None

    null_bits: list[bool] = [False] * row_count
    null_hdr = _parse_array_header(data, null_ref)
    if null_hdr and not null_hdr["has_refs"] and null_hdr["width"] == 1:
        null_payload = data[null_ref + 8 : null_ref + 8 + null_hdr["Payload bytes (raw)"]]
        for i in range(row_count):
            byte_i, bit_i = divmod(i, 8)
            if byte_i < len(null_payload):
                null_bits[i] = bool((null_payload[byte_i] >> bit_i) & 1)

    results: list[str | None] = []
    for i in range(row_count):
        if null_bits[i]:
            results.append(None)
            continue
        start = _read_ref(data, offs_ref + 8, i, offs_eb)
        end = _read_ref(data, offs_ref + 8, i + 1, offs_eb)
        if start < 0 or end < start or end > len(blob):
            results.append(None)
            continue
        chunk = blob[start:end]
        results.append(f"<blob {len(chunk)}B: {chunk[:16].hex()}" + ("…" if len(chunk) > 16 else "") + ">")

    return results


def _read_direct_string_column(
    data: bytes,
    col_offset: int,
    file_size: int,
    expected_rows: int | None = None,
) -> list[str | None] | None:
    """Parse a Realm string column stored as a flat per-row ref-array.

    Covers two sub-formats that share the same outer shape (has_refs=True,
    count = N rows, each element = file offset):

    * **Raw pointer** — offset points directly to a null-terminated UTF-8
      byte sequence (no array header).
    * **Inline scheme=2 array** — offset points to a Realm array header
      (AAAA) with width_scheme=2; the array payload is the string bytes.
      The ``size`` field gives the byte count (may or may not be
      null-terminated).

    Both sub-formats are distinguished from the canonical 3-entry string leaf
    by having count ≠ 3, and from blob columns because there is no N+1 offsets
    array wrapping.

    Returns a list of N strings (``None`` for null/out-of-range rows), or
    ``None`` if the column doesn't match either sub-format.
    """
    hdr = _parse_array_header(data, col_offset)
    if hdr is None or not hdr["has_refs"]:
        return None
    # 3-entry refs are string/blob columns, handled elsewhere
    count = hdr["Element count (size)"]
    if count == 3:
        return None
    if expected_rows is not None and count != expected_rows:
        return None

    eb = _elem_bytes(hdr)
    if eb < 1:
        return None

    results: list[str | None] = []
    valid = 0
    mode: str | None = None  # "raw" | "scheme2" | None (not yet determined)

    for i in range(count):
        str_off = _read_ref(data, col_offset + 8, i, eb)
        if str_off <= 0 or str_off >= file_size:
            results.append(None)
            continue

        if data[str_off : str_off + 4] == b"\x41\x41\x41\x41":
            # Target is a Realm array — must be scheme=2 to be a string
            if mode == "raw":
                return None  # inconsistent
            mode = "scheme2"
            child = _parse_array_header(data, str_off)
            if child is None or child["width_scheme"] != 2:
                results.append(None)
                continue
            size = child["Element count (size)"]
            raw_bytes = data[str_off + 8 : str_off + 8 + size]
            null_pos = raw_bytes.find(b"\x00")
            raw = raw_bytes[:null_pos] if null_pos >= 0 else raw_bytes
        else:
            # Target is a raw null-terminated string in the file body
            if mode == "scheme2":
                return None  # inconsistent
            mode = "raw"
            chunk = data[str_off : str_off + 512]
            null_pos = chunk.find(b"\x00")
            raw = chunk[:null_pos] if null_pos >= 0 else chunk

        try:
            s = raw.decode("utf-8", errors="strict")
            results.append(s)
            valid += 1
        except UnicodeDecodeError:
            results.append(None)

    # Require at least one successfully decoded string to commit
    if valid == 0 and count > 0:
        return None
    return results


def _derive_row_count(
    data: bytes,
    col_data_ref: int,
    num_cols: int,
    cd_eb: int,
    file_size: int,
) -> int | None:
    """Derive the table row count from the most common element-count across leaf data arrays.

    The canonical child[7] approach is unreliable in practice (it sometimes
    stores a different bitmap). The actual row count equals the element count
    of the column data arrays themselves.
    """
    from collections import Counter
    counts: list[int] = []
    for c_idx in range(num_cols):
        col_ref = _read_ref(data, col_data_ref + 8, c_idx, cd_eb)
        if col_ref <= 0 or col_ref >= file_size:
            continue
        hdr = _parse_array_header(data, col_ref)
        if hdr and not hdr["has_refs"]:
            counts.append(hdr["Element count (size)"])
    if not counts:
        return None
    return Counter(counts).most_common(1)[0][0]


def _extract_table_data(
    data: bytes,
    root_offset: int,
    schema: list[str],
    file_size: int,
) -> list[dict[str, Any]]:
    """Walk the B+ tree and extract column data for each table.

    Path: root_offset → child[1] (table refs) → table_node → child[2]
          (column data arrays) → leaf nodes → decoded values.

    Handles string (3-entry leaf), blob (N+1 offsets leaf), per-row direct
    string refs, and scalar (integer/boolean) columns.

    Returns a list of dicts ``{name, row_count, columns}`` where
    ``columns`` is a dict of ``{col_index: [values]}``.
    """
    root_hdr = _parse_array_header(data, root_offset)
    if root_hdr is None or not root_hdr["has_refs"]:
        return []

    root_eb = _elem_bytes(root_hdr)
    if root_eb < 1 or root_hdr["Element count (size)"] < 2:
        return []

    # child[1] of root = table refs array
    table_refs_off = _read_ref(data, root_offset + 8, 1, root_eb)
    if table_refs_off <= 0 or table_refs_off >= file_size:
        return []

    tr_hdr = _parse_array_header(data, table_refs_off)
    if tr_hdr is None or not tr_hdr["has_refs"]:
        return []
    tr_eb = _elem_bytes(tr_hdr)
    num_tables = tr_hdr["Element count (size)"]

    tables: list[dict[str, Any]] = []

    for t_idx in range(num_tables):
        table_ref = _read_ref(data, table_refs_off + 8, t_idx, tr_eb)
        if table_ref <= 0 or table_ref >= file_size:
            continue

        t_hdr = _parse_array_header(data, table_ref)
        if t_hdr is None or not t_hdr["has_refs"] or t_hdr["Element count (size)"] < 3:
            continue

        t_eb = _elem_bytes(t_hdr)

        # child[2] = column data array
        col_data_ref = _read_ref(data, table_ref + 8, 2, t_eb)
        if col_data_ref <= 0 or col_data_ref >= file_size:
            continue

        cd_hdr = _parse_array_header(data, col_data_ref)
        if cd_hdr is None or not cd_hdr["has_refs"]:
            continue

        cd_eb = _elem_bytes(cd_hdr)
        num_cols = cd_hdr["Element count (size)"]

        # Derive row count from the most common element count across data arrays.
        # The child[7]-based approach is unreliable across Realm format versions.
        row_count: int | None = _derive_row_count(
            data, col_data_ref, num_cols, cd_eb, file_size
        )

        columns: dict[int, list[Any]] = {}
        for c_idx in range(num_cols):
            col_ref = _read_ref(data, col_data_ref + 8, c_idx, cd_eb)
            if col_ref <= 0 or col_ref >= file_size:
                continue
            values: list[Any] | None = _read_string_leaf(data, col_ref, file_size, row_count)
            if values is None:
                values = _read_blob_leaf(data, col_ref, file_size, row_count)
            if values is None:
                values = _read_direct_string_column(data, col_ref, file_size, row_count)
            if values is None:
                values = _read_scalar_leaf(data, col_ref, file_size)
            if values is not None:
                columns[c_idx] = values

        if columns or row_count is not None:
            tables.append(
                {
                    "name": schema[t_idx] if t_idx < len(schema) else f"table[{t_idx}]",
                    "row_count": row_count,
                    "columns": columns,
                }
            )

    return tables


# ---------------------------------------------------------------------------
# String scanner
# ---------------------------------------------------------------------------

# Matches runs of printable ASCII and UTF-8 2-/3-byte sequences (Latin, Greek, …).
# This surfaces human-readable content stored in Data Arrays without requiring
# full B+ tree traversal or column-type knowledge.
_STRING_RUN = re.compile(
    rb"(?:[\x20-\x7E]|[\xC2-\xDF][\x80-\xBF]|[\xE0-\xEF][\x80-\xBF]{2}){8,}"
)


def _scan_strings(data: bytes, min_len: int = 20) -> list[str]:
    """Return unique printable strings (ASCII + UTF-8) found in *data*."""
    results: list[str] = []
    seen: set[str] = set()
    for m in _STRING_RUN.finditer(data):
        try:
            s = m.group().decode("utf-8", errors="replace").strip()
        except Exception:
            continue
        if len(s) >= min_len and s not in seen:
            seen.add(s)
            results.append(s)
    return results


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class RealmParser(AbstractParser):
    SUPPORTED_EXTENSIONS = [".realm"]
    DISPLAY_NAME = "Realm Database"

    def can_parse(self, path: str, peek_bytes: bytes) -> bool:
        if len(peek_bytes) >= _HEADER_SIZE and peek_bytes[16:20] == _MNEMONIC:
            return True
        return self._ext_match(path)

    # Cap for the hex-preview panel; full file is read separately for structure analysis
    _HEX_PREVIEW_BYTES = 1024 * 256  # 256 KB

    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        # Read the full file so columns near the end of large Realm files are not missed.
        # A separate 256 KB slice is kept for the HexViewer tab.
        with vfs.open(node) as src:
            full_data = src.read()
        preview = full_data[: self._HEX_PREVIEW_BYTES]

        header_info = _parse_realm_header(full_data)

        top_refs: dict[str, Any] = {}
        schema: list[str] = []
        active_idx = 0

        if header_info:
            top_ref0_val = int.from_bytes(full_data[0:8], "little")
            top_ref1_val = int.from_bytes(full_data[8:16], "little")
            active_idx = header_info["Active top reference"]

            hdr0 = _parse_array_header(full_data, top_ref0_val)
            hdr1 = _parse_array_header(full_data, top_ref1_val)
            children0 = _extract_root_children(full_data, top_ref0_val, node.size)
            children1 = _extract_root_children(full_data, top_ref1_val, node.size)

            top_refs = {
                "top_ref_0": {
                    "offset": top_ref0_val,
                    "active": active_idx == 0,
                    "array_header": hdr0,
                    "children": children0,
                },
                "top_ref_1": {
                    "offset": top_ref1_val,
                    "active": active_idx == 1,
                    "array_header": hdr1,
                    "children": children1,
                },
                "active_index": active_idx,
            }

            active_offset = top_ref1_val if active_idx == 1 else top_ref0_val
            schema = _extract_schema(full_data, active_offset, node.size)

        strings = _scan_strings(full_data)

        tables: list[dict[str, Any]] = []
        if header_info and schema:
            tables = _extract_table_data(full_data, active_offset, schema, node.size)

        data: dict[str, Any] = {
            "header": header_info,
            "preview": preview,
            "top_refs": top_refs,
            "schema": schema,
            "tables": tables,
            "strings": strings,
        }

        meta: dict[str, Any] = {
            "Format": "Realm Database",
            "File size": f"{node.size:,} B",
        }
        if header_info:
            meta["Header mnemonic"] = header_info.get("Mnemonic", "?")
            meta["File format"] = (
                f"{header_info['File format (top ref 0)']}/"
                f"{header_info['File format (top ref 1)']}"
            )
            meta["Active top ref"] = str(active_idx)
            if schema:
                meta["Tables found"] = str(len(schema))
        else:
            meta["Header"] = "Not detected (possibly encrypted or non-standard)"

        return ParseResult(viewer_type="realm", data=data, metadata=meta)
