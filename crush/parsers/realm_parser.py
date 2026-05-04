# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Realm database parser — header + array structure decoding."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import AbstractParser, ParseResult

_HEADER_SIZE = 24
_MNEMONIC = b"T-DB"

# width_ndx (bits [2:0] of array flags byte) → element width value
# Scheme 0: width is in bits.  Scheme 1: width is in bytes.
_WIDTH_TABLE = [0, 1, 2, 4, 8, 16, 32, 64]

# Realm ColumnType codes stored in spec→child[0]
_REALM_COL_TYPES: dict[int, str] = {
    0: "int",
    1: "bool",
    2: "string",
    4: "data",
    6: "mixed",
    8: "date",
    9: "float",
    10: "double",
    11: "decimal128",
    12: "link",
    13: "linklist",
    14: "backlink",
    15: "objectId",
    16: "typedlink",
    17: "uuid",
}

# Column types that are hidden (no user-visible name) and must be skipped
_HIDDEN_COL_TYPES: frozenset[int] = frozenset({14})  # BackLink


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

def _read_uint_array(data: bytes, offset: int) -> list[int]:
    """Read all unsigned integer values from a Realm integer array at *offset*."""
    hdr = _parse_array_header(data, offset)
    if not hdr:
        return []
    count = hdr["Element count (size)"]
    width = hdr["width"]
    scheme = hdr["width_scheme"]
    if count == 0 or width == 0:
        return []
    payload = data[offset + 8:]
    vals: list[int] = []
    if scheme == 0:
        # bit-packed
        for i in range(count):
            bit_off = i * width
            byte_off = bit_off // 8
            eb = (width + 7) // 8
            if byte_off + eb > len(payload):
                break
            v = int.from_bytes(payload[byte_off : byte_off + eb], "little")
            mask = (1 << width) - 1
            vals.append((v >> (bit_off % 8)) & mask)
    elif scheme == 1:
        eb = width
        for i in range(count):
            if (i + 1) * eb > len(payload):
                break
            vals.append(int.from_bytes(payload[i * eb : (i + 1) * eb], "little"))
    return vals


def _extract_free_list(
    data: bytes, root_offset: int, file_size: int
) -> list[dict[str, Any]]:
    """Extract the Realm free-space list from a root reference array.

    Realm's Group node stores three parallel arrays at child indices 3/4/5:
      child[3] — file positions of freed blocks
      child[4] — byte sizes of freed blocks
      child[5] — database version when each block was freed

    Returns a list of dicts with keys:
      offset, size, version, array_header (or None), strings (list[str]), bytes
    """
    root_hdr = _parse_array_header(data, root_offset)
    if root_hdr is None or not root_hdr["has_refs"]:
        return []
    ref_eb = _elem_bytes(root_hdr)
    if ref_eb < 1 or root_hdr["Element count (size)"] < 6:
        return []
    payload_start = root_offset + 8
    pos_off = _read_ref(data, payload_start, 3, ref_eb)
    sz_off  = _read_ref(data, payload_start, 4, ref_eb)
    ver_off = _read_ref(data, payload_start, 5, ref_eb)

    positions = _read_uint_array(data, pos_off)
    sizes     = _read_uint_array(data, sz_off)
    versions  = _read_uint_array(data, ver_off)

    entries: list[dict[str, Any]] = []
    for i, (pos, sz) in enumerate(zip(positions, sizes)):
        if pos <= 0 or sz <= 0 or pos + sz > len(data):
            continue
        block = data[pos : pos + sz]
        arr_hdr = _parse_array_header(data, pos)
        strings: list[str] = []
        if arr_hdr is None:
            # Raw heap — extract null-separated printable strings (≥4 chars)
            for chunk in block.split(b"\x00"):
                try:
                    s = chunk.decode("utf-8")
                    if len(s) >= 4 and s.isprintable():
                        strings.append(s)
                except Exception:
                    pass
        entries.append({
            "index": i,
            "offset": pos,
            "size": sz,
            "version": versions[i] if i < len(versions) else None,
            "array_header": arr_hdr,
            "strings": strings,
            "bytes": block,
        })
    return entries


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
    if hdr is None:
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
            # For byte-aligned widths, Realm stores signed int64_t values.
            # Reinterpret as two's-complement signed so values stay within
            # qlonglong range and do not cause OverflowError in Qt.
            sign_bit = (1 << (width - 1)) if width >= 8 else 0
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
                val = (raw >> bit_off) & mask
                if sign_bit and val >= sign_bit:
                    val -= (1 << width)
                result.append(val)
            # 2-bit scheme=0 is Realm's nullable boolean: 0=False, 1=True, ≥2=NULL
            if width == 2:
                result = [None if v is None or v >= 2 else bool(v) for v in result]
            return result

    elif scheme == 1:
        eb = int(width)
        if eb < 1 or eb > 8:
            return None
        result = []
        for i in range(count):
            off = payload_start + i * eb
            if off + eb > len(data):
                result.append(None)
            else:
                # signed=True: Realm uses int64_t for all integer columns
                result.append(int.from_bytes(data[off : off + eb], "little", signed=True))
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


def _read_inline_string_leaf(
    data: bytes,
    col_offset: int,
) -> list[str | None] | None:
    """Parse a Realm format-24 inline string column (scheme=1, any byte-width).

    General encoding for a W-byte entry:
      - bytes [0 .. length-1]: UTF-8 string content (up to W-1 chars)
      - byte [W-1]: padding count; actual length = (W-1) - pad
      - pad >= W → NULL value (all content bytes are zero) or heap pointer
    Validated against integer columns: if any non-null entry contains a null
    byte in its content region, the whole column is rejected (→ None).
    Returns None if the array does not match this layout.
    """
    hdr = _parse_array_header(data, col_offset)
    if hdr is None or hdr["has_refs"] or hdr["width_scheme"] != 1:
        return None

    width = hdr["width"]
    if width < 8:
        return None

    count = hdr["Element count (size)"]
    if count == 0:
        return []

    max_len = width - 1
    payload_start = col_offset + 8
    results: list[str | None] = []
    valid = 0

    for i in range(count):
        off = payload_start + i * width
        if off + width > len(data):
            results.append(None)
            continue
        entry = data[off : off + width]
        pad = entry[width - 1]
        if pad >= width:
            # NULL: content bytes all zero; otherwise heap pointer
            if entry[:max_len] == b"\x00" * max_len:
                results.append(None)
            else:
                results.append("<long>")
            valid += 1
        else:
            length = max_len - pad
            raw = entry[:length] if length > 0 else b""
            # Reject if content has null bytes — integers stored in scheme=1
            # arrays often produce null bytes here, signalling a non-string column.
            if b"\x00" in raw:
                return None
            try:
                s = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                return None
            results.append(s)
            valid += 1

    return results if valid > 0 else None


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
    # Refs narrower than 32 bits are integer link keys, not file-offset string pointers
    if hdr["width"] < 32:
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


def _decode_timestamp(val: int) -> str:
    """Convert a Realm Timestamp integer to a readable UTC string.

    Realm format 24 stores the seconds part of Timestamp as an int64.
    Auto-detects unit by magnitude: seconds → milliseconds → nanoseconds.
    Falls back to the raw integer string if the value is out of any useful range.
    """
    try:
        if 0 < val < 10_000_000_000:          # seconds (1970 – ~2286)
            dt = datetime.fromtimestamp(val, tz=timezone.utc)
        elif 0 < val < 10_000_000_000_000:    # milliseconds
            dt = datetime.fromtimestamp(val / 1_000, tz=timezone.utc)
        elif 0 < val < 10_000_000_000_000_000_000:  # nanoseconds
            dt = datetime.fromtimestamp(val / 1_000_000_000, tz=timezone.utc)
        else:
            return str(val)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (OSError, OverflowError, ValueError):
        return str(val)


def _read_nullable_integer_column(
    data: bytes,
    col_offset: int,
    file_size: int,
    expected_rows: int | None = None,
) -> list[int | None] | None:
    """Parse a nullable integer/date column stored as a 2-entry ref array.

    Format: outer ref array with count=2:
        ref[0] → values Data Array (scheme=0, count=expected_rows)
        ref[1] → null bitmap (scheme=0, width=1, count=expected_rows; 1 = NULL)

    Used for Realm nullable int, date, float, double, objectId, uuid, etc.
    """
    hdr = _parse_array_header(data, col_offset)
    if hdr is None or not hdr["has_refs"] or hdr["Element count (size)"] != 2:
        return None

    eb = _elem_bytes(hdr)
    if eb < 1:
        return None

    values_ref = _read_ref(data, col_offset + 8, 0, eb)
    null_ref = _read_ref(data, col_offset + 8, 1, eb)

    if values_ref <= 0 or values_ref >= file_size:
        return None
    if null_ref <= 0 or null_ref >= file_size:
        return None

    null_hdr = _parse_array_header(data, null_ref)
    if (
        null_hdr is None
        or null_hdr["has_refs"]
        or null_hdr["width"] != 1
        or null_hdr["width_scheme"] != 0
    ):
        return None

    vals_hdr = _parse_array_header(data, values_ref)
    if vals_hdr is None or vals_hdr["has_refs"]:
        return None

    null_count = null_hdr["Element count (size)"]
    vals_count = vals_hdr["Element count (size)"]
    if null_count != vals_count:
        return None
    if expected_rows is not None and null_count != expected_rows:
        return None

    null_payload = data[null_ref + 8 : null_ref + 8 + null_hdr["Payload bytes (raw)"]]
    null_bits: list[bool] = []
    for i in range(null_count):
        byte_i, bit_i = divmod(i, 8)
        null_bits.append(
            bool((null_payload[byte_i] >> bit_i) & 1)
            if byte_i < len(null_payload)
            else False
        )

    values_list = _read_scalar_leaf(data, values_ref, file_size)
    if values_list is None:
        return None

    result: list[int | None] = []
    for i in range(null_count):
        if null_bits[i]:
            result.append(None)
        elif i < len(values_list):
            result.append(values_list[i])
        else:
            result.append(None)
    return result


def _read_timestamp_column(
    data: bytes,
    col_offset: int,
    file_size: int,
    expected_rows: int | None = None,
) -> list[str | None] | None:
    """Parse a Realm Timestamp column stored as a 2-entry ref array.

    Format: outer ref array count=2:
        ref[0] → seconds array (scheme=0, w≥8, 1-indexed; position 0 = INT_MAX null sentinel)
        ref[1] → nanoseconds array (scheme=0, any w; 0-indexed, same count = expected_rows)

    Row i maps to secs_vals[i+1].  Sentinel value (max signed for given width) → NULL.
    """
    hdr = _parse_array_header(data, col_offset)
    if hdr is None or not hdr["has_refs"] or hdr["Element count (size)"] != 2:
        return None

    eb = _elem_bytes(hdr)
    if eb < 1:
        return None

    secs_ref = _read_ref(data, col_offset + 8, 0, eb)
    nanos_ref = _read_ref(data, col_offset + 8, 1, eb)

    if secs_ref <= 0 or secs_ref >= file_size:
        return None

    secs_hdr = _parse_array_header(data, secs_ref)
    if secs_hdr is None or secs_hdr["has_refs"] or secs_hdr["width"] < 8:
        return None

    secs_count = secs_hdr["Element count (size)"]
    # 1-indexed: position 0 is the null-sentinel slot; actual rows are 1..secs_count-1
    actual_rows = secs_count - 1
    if actual_rows < 0:
        return None
    if expected_rows is not None and actual_rows != expected_rows:
        return None

    secs_vals = _read_scalar_leaf(data, secs_ref, file_size)
    if secs_vals is None:
        return None

    # Nanoseconds — optional, ignored if width=0 (all zeros)
    nanos_vals: list[Any] | None = None
    if 0 < nanos_ref < file_size:
        nanos_hdr = _parse_array_header(data, nanos_ref)
        if nanos_hdr and not nanos_hdr["has_refs"] and nanos_hdr["width"] >= 8:
            nanos_vals = _read_scalar_leaf(data, nanos_ref, file_size)

    width = secs_hdr["width"]
    null_sentinel = (1 << (width - 1)) - 1  # INT32_MAX for w=32, INT64_MAX for w=64

    result: list[str | None] = []
    for i in range(actual_rows):
        idx = i + 1
        s = secs_vals[idx] if idx < len(secs_vals) else None
        if s is None or s == null_sentinel:
            result.append(None)
        else:
            ns = 0
            if nanos_vals and i < len(nanos_vals):
                ns = nanos_vals[i] or 0
            ts = s + (ns / 1_000_000_000 if ns else 0)
            result.append(_decode_timestamp(int(ts)))
    return result


def _extract_column_names(
    data: bytes,
    table_ref: int,
    table_eb: int,
    file_size: int,
) -> list[str]:
    """Read column names from the spec at child[0] of the table node.

    Path: table_ref → child[0] (spec) → child[1] (names Data Array).
    spec child[0] holds column type codes; child[1] holds fixed-width 32-byte
    null-terminated ASCII names for user-visible columns (ObjKey is omitted).
    Returns an empty list on any failure.
    """
    spec_ref = _read_ref(data, table_ref + 8, 0, table_eb)
    if spec_ref <= 0 or spec_ref >= file_size:
        return []
    spec_hdr = _parse_array_header(data, spec_ref)
    if spec_hdr is None or not spec_hdr["has_refs"] or spec_hdr["Element count (size)"] < 2:
        return []
    spec_eb = _elem_bytes(spec_hdr)
    if spec_eb < 1:
        return []

    # child[1] = column names (scheme=1, width=32, fixed-width ASCII)
    names_ref = _read_ref(data, spec_ref + 8, 1, spec_eb)
    if names_ref <= 0 or names_ref >= file_size:
        return []
    names_hdr = _parse_array_header(data, names_ref)
    if names_hdr is None or names_hdr["has_refs"]:
        return []

    entry_bytes = _elem_bytes(names_hdr)
    count = names_hdr["Element count (size)"]
    if entry_bytes < 1 or count == 0:
        return []

    payload_start = names_ref + 8
    names: list[str] = []
    for i in range(count):
        entry_off = payload_start + i * entry_bytes
        if entry_off + entry_bytes > len(data):
            break
        entry = data[entry_off : entry_off + entry_bytes]
        null_pos = entry.find(b"\x00")
        raw = entry[:null_pos] if null_pos >= 0 else entry
        try:
            name = raw.decode("ascii").strip()
        except Exception:
            name = f"col_{i}"
        names.append(name if name else f"col_{i}")
    return names


def _extract_column_types(
    data: bytes,
    table_ref: int,
    table_eb: int,
    file_size: int,
) -> list[int]:
    """Read column type codes from spec→child[0].

    Path: table_ref → child[0] (spec) → child[0] (type codes Data Array).
    Returns a list of integer type codes aligned with the column names list.
    Returns an empty list on any failure.
    """
    spec_ref = _read_ref(data, table_ref + 8, 0, table_eb)
    if spec_ref <= 0 or spec_ref >= file_size:
        return []
    spec_hdr = _parse_array_header(data, spec_ref)
    if spec_hdr is None or not spec_hdr["has_refs"] or spec_hdr["Element count (size)"] < 1:
        return []
    spec_eb = _elem_bytes(spec_hdr)
    if spec_eb < 1:
        return []

    types_ref = _read_ref(data, spec_ref + 8, 0, spec_eb)
    if types_ref <= 0 or types_ref >= file_size:
        return []

    codes = _read_scalar_leaf(data, types_ref, file_size)
    if codes is None:
        return []
    return [int(c) for c in codes if c is not None]


def _extract_column_key_map(
    data: bytes,
    table_ref: int,
    table_eb: int,
    file_size: int,
    raw_type_codes: list[int],
) -> dict[int, int] | None:
    """Build a cluster-index → user-column-index map from spec→child[5] colkeys.

    Each column key encodes its physical cluster position:
        cluster_idx = (colkey & 0xFFFF) + 1
    Entries whose type code is in _HIDDEN_COL_TYPES (e.g. BackLink = 14) are skipped.
    Returns None if spec has fewer than 6 children or colkeys cannot be read.
    """
    spec_ref = _read_ref(data, table_ref + 8, 0, table_eb)
    if spec_ref <= 0 or spec_ref >= file_size:
        return None
    spec_hdr = _parse_array_header(data, spec_ref)
    if spec_hdr is None or not spec_hdr["has_refs"] or spec_hdr["Element count (size)"] < 6:
        return None
    spec_eb = _elem_bytes(spec_hdr)
    if spec_eb < 1:
        return None

    colkeys_ref = _read_ref(data, spec_ref + 8, 5, spec_eb)
    if colkeys_ref <= 0 or colkeys_ref >= file_size:
        return None

    colkeys = _read_scalar_leaf(data, colkeys_ref, file_size)
    if not colkeys:
        return None

    key_map: dict[int, int] = {}
    user_col_idx = 0
    for i, colkey in enumerate(colkeys):
        if colkey is None:
            continue
        type_code = raw_type_codes[i] if i < len(raw_type_codes) else -1
        if type_code in _HIDDEN_COL_TYPES:
            continue
        cluster_idx = (int(colkey) & 0xFFFF) + 1
        key_map[cluster_idx] = user_col_idx
        user_col_idx += 1

    return key_map if key_map else None


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
        num_cluster = cd_hdr["Element count (size)"]

        # Cluster[0] is the ObjKey array — the most reliable source for row count.
        # ObjKey is always a non-ref scalar array with exactly one entry per row.
        # Falls back to the statistical heuristic if cluster[0] can't be read.
        obj_keys: list[Any] | None = None
        row_count: int | None = None
        obj_key_ref = _read_ref(data, col_data_ref + 8, 0, cd_eb)
        if 0 < obj_key_ref < file_size:
            ok_hdr = _parse_array_header(data, obj_key_ref)
            if ok_hdr and not ok_hdr["has_refs"]:
                row_count = ok_hdr["Element count (size)"]
                obj_keys = _read_scalar_leaf(data, obj_key_ref, file_size)
        if row_count is None:
            row_count = _derive_row_count(data, col_data_ref, num_cluster, cd_eb, file_size)

        # Column names and types from spec (user-visible columns, excludes ObjKey).
        col_names = _extract_column_names(data, table_ref, t_eb, file_size)
        raw_type_codes = _extract_column_types(data, table_ref, t_eb, file_size)
        n_names = len(col_names)
        # col_type_codes aligned with user column names: remove BackLink entries,
        # then take the first n_names to match the names list.
        col_type_codes = [tc for tc in raw_type_codes if tc not in _HIDDEN_COL_TYPES]
        if n_names > 0:
            col_type_codes = col_type_codes[:n_names]

        # Build a cluster-index → user-col-index map using spec→child[5] colkeys.
        # Falls back to the "last N" heuristic when colkeys are unavailable.
        key_map: dict[int, int] | None = None
        if n_names > 0:
            key_map = _extract_column_key_map(data, table_ref, t_eb, file_size, raw_type_codes)
            if key_map is None and num_cluster >= n_names:
                col_start = num_cluster - n_names
                key_map = {col_start + i: i for i in range(n_names)}

        columns: dict[int, list[Any]] = {}
        for c_idx in range(num_cluster):
            col_ref = _read_ref(data, col_data_ref + 8, c_idx, cd_eb)
            if col_ref <= 0 or col_ref >= file_size:
                continue

            # Determine if this cluster entry is a user column.
            if n_names > 0:
                user_col_idx = key_map.get(c_idx) if key_map is not None else None
                if user_col_idx is None:
                    continue  # ObjKey, BackLink, or other internal column
                type_code = col_type_codes[user_col_idx] if user_col_idx < len(col_type_codes) else -1
            else:
                user_col_idx = None
                type_code = -1

            # Decode the column data; timestamp columns use a dedicated decoder.
            values: list[Any] | None
            if type_code == 8:  # Timestamp
                values = _read_timestamp_column(data, col_ref, file_size, row_count)
                if values is None:
                    values = _read_scalar_leaf(data, col_ref, file_size)
            else:
                values = _read_inline_string_leaf(data, col_ref)
                if values is None:
                    values = _read_string_leaf(data, col_ref, file_size, row_count)
                if values is None:
                    values = _read_blob_leaf(data, col_ref, file_size, row_count)
                if values is None:
                    values = _read_direct_string_column(data, col_ref, file_size, row_count)
                if values is None:
                    values = _read_nullable_integer_column(data, col_ref, file_size, row_count)
                if values is None:
                    values = _read_scalar_leaf(data, col_ref, file_size)

            if n_names > 0 and user_col_idx is not None:
                # NULL-only columns: emit all-None list so the column appears in output.
                columns[user_col_idx] = values if values is not None else [None] * (row_count or 0)
            elif n_names == 0:
                # No names available: expose all sub-arrays with raw cluster indices.
                if values is not None:
                    columns[c_idx] = values

        col_type_names = [_REALM_COL_TYPES.get(c, f"type_{c}") for c in col_type_codes]

        if columns or row_count is not None:
            tables.append(
                {
                    "name": schema[t_idx] if t_idx < len(schema) else f"table[{t_idx}]",
                    "row_count": row_count,
                    "columns": columns,
                    "column_names": col_names,
                    "column_types": col_type_names,
                    "obj_keys": obj_keys,
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
        inactive_schema: list[str] = []
        inactive_ref_idx: int = 0
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
            inactive_offset = top_ref0_val if active_idx == 1 else top_ref1_val
            inactive_ref_idx = 0 if active_idx == 1 else 1
            schema = _extract_schema(full_data, active_offset, node.size)
            inactive_schema = _extract_schema(full_data, inactive_offset, node.size)

        strings = _scan_strings(full_data)

        tables: list[dict[str, Any]] = []
        if header_info and schema:
            tables = _extract_table_data(full_data, active_offset, schema, node.size)

        inactive_tables: list[dict[str, Any]] = []
        if header_info and inactive_schema:
            inactive_tables = _extract_table_data(
                full_data, inactive_offset, inactive_schema, node.size
            )

        # Inject schema-level diff into top_refs so the viewer can display it.
        if top_refs and (schema or inactive_schema):
            active_set = set(schema)
            inactive_set = set(inactive_schema)
            active_rows = {t["name"]: t.get("row_count", 0) for t in tables}
            inactive_rows = {t["name"]: t.get("row_count", 0) for t in inactive_tables}
            changed: dict[str, str] = {}
            for name in active_set & inactive_set:
                ar = active_rows.get(name, 0) or 0
                ir = inactive_rows.get(name, 0) or 0
                if ar != ir:
                    changed[name] = f"active={ar}  vs  inactive={ir}"
            top_refs["schema_diff"] = {
                "only_in_active": sorted(active_set - inactive_set),
                "only_in_inactive": sorted(inactive_set - active_set),
                "row_count_changed": changed,
            }

        # Free-list extraction from both refs — merged with source tagging.
        freed_blocks: list[dict[str, Any]] = []
        if header_info:
            active_fl  = _extract_free_list(full_data, active_offset,   node.size)
            inactive_fl = _extract_free_list(full_data, inactive_offset, node.size)
            # Merge: prefer the entry object from whichever ref has it;
            # "both" wins over individual, active-only appears last (most recently freed)
            seen: dict[tuple[int, int], dict[str, Any]] = {}
            for entry in inactive_fl:
                k = (entry["offset"], entry["size"])
                entry["source"] = "inactive"
                seen[k] = entry
            for entry in active_fl:
                k = (entry["offset"], entry["size"])
                if k in seen:
                    seen[k] = dict(seen[k])
                    seen[k]["source"] = "both"
                else:
                    entry["source"] = "active"
                    seen[k] = entry
            freed_blocks = sorted(seen.values(), key=lambda e: e["offset"])

        data: dict[str, Any] = {
            "header": header_info,
            "preview": preview,
            "top_refs": top_refs,
            "schema": schema,
            "tables": tables,
            "inactive_schema": inactive_schema,
            "inactive_tables": inactive_tables,
            "inactive_ref_index": inactive_ref_idx if header_info else None,
            "strings": strings,
            "freed_blocks": freed_blocks,
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

        text_parts: list[str] = []
        for t in tables:
            for vals in t.get("columns", {}).values():
                for v in vals:
                    if isinstance(v, str) and v.strip() and not v.startswith("<blob"):
                        text_parts.append(v)
        text_parts.extend(strings[:500])

        return ParseResult(
            viewer_type="realm",
            data=data,
            metadata=meta,
            text_index=" ".join(text_parts[:2000]),
        )
