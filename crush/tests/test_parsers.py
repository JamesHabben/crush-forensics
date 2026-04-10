# SPDX-License-Identifier: Apache-2.0
"""Tests for built-in parsers."""
from __future__ import annotations

import plistlib
import sqlite3
from pathlib import Path


from crush.core.vfs import DirectoryVFS
from crush.parsers.sqlite_parser import SQLiteParser
from crush.parsers.plist_parser import PlistParser
from crush.parsers.abx_parser import AbxParser
from crush.parsers.hex_fallback import HexFallbackParser
from crush.parsers.realm_parser import RealmParser
from crush.core.encodings import detect_encoding as _detect_encoding


def _make_sqlite(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, text TEXT)")
    conn.execute("INSERT INTO messages (text) VALUES ('hello')")
    conn.commit()
    conn.close()


def test_sqlite_parser_can_parse(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _make_sqlite(db_path)

    vfs = DirectoryVFS(tmp_path)
    root = vfs.root()
    node = next(c for c in root.children if c.name == "test.db")

    parser = SQLiteParser()
    assert parser.can_parse(node.path, vfs.peek(node))


def test_sqlite_parser_parse(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _make_sqlite(db_path)

    vfs = DirectoryVFS(tmp_path)
    root = vfs.root()
    node = next(c for c in root.children if c.name == "test.db")

    parser = SQLiteParser()
    result = parser.parse(node, vfs)

    assert result.viewer_type == "table"
    assert "messages" in result.data
    assert result.data["messages"]["columns"][1] == "text"
    assert result.data["messages"]["rows"][0][1] == "hello"


def test_plist_parser_binary(tmp_path: Path) -> None:
    data = {"key": "value", "number": 42}
    plist_path = tmp_path / "test.plist"
    plist_path.write_bytes(plistlib.dumps(data, fmt=plistlib.FMT_BINARY))

    vfs = DirectoryVFS(tmp_path)
    root = vfs.root()
    node = next(c for c in root.children if c.name == "test.plist")

    parser = PlistParser()
    assert parser.can_parse(node.path, vfs.peek(node))

    result = parser.parse(node, vfs)
    assert result.viewer_type == "tree"
    assert result.data["key"] == "value"
    assert result.metadata["Format"] == "binary"


def test_hex_fallback_always_matches() -> None:
    parser = HexFallbackParser()
    assert parser.can_parse("anything.xyz", b"\x00\x01\x02\x03")


def test_hex_fallback_parse(tmp_path: Path) -> None:
    raw = bytes(range(64))
    (tmp_path / "blob.bin").write_bytes(raw)

    vfs = DirectoryVFS(tmp_path)
    root = vfs.root()
    node = next(c for c in root.children if c.name == "blob.bin")

    parser = HexFallbackParser()
    result = parser.parse(node, vfs)
    assert result.viewer_type == "hex"
    assert result.data == raw


def _make_realm_header(
    top_ref0: int = 212880,
    top_ref1: int = 211736,
    fmt0: int = 24,
    fmt1: int = 24,
    reserved: int = 0,
    flag: int = 0,
) -> bytes:
    return (
        top_ref0.to_bytes(8, "little") +
        top_ref1.to_bytes(8, "little") +
        b"T-DB" +
        bytes([fmt0, fmt1, reserved, flag])
    )


def test_realm_parser_header(tmp_path: Path) -> None:
    realm_path = tmp_path / "default.realm"
    realm_path.write_bytes(_make_realm_header() + b"\x00" * 512)

    vfs = DirectoryVFS(tmp_path)
    root = vfs.root()
    node = next(c for c in root.children if c.name == "default.realm")

    parser = RealmParser()
    assert parser.can_parse(node.path, vfs.peek(node))

    result = parser.parse(node, vfs)
    assert result.viewer_type == "realm"
    assert "header" in result.data
    header = result.data["header"]
    assert header["Mnemonic"] == "T-DB"
    assert header["File format (top ref 0)"] == 24

    # New data structure: top_refs and schema
    assert "top_refs" in result.data
    assert "schema" in result.data
    # top_ref entries exist even when array headers are not reachable (synthetic file)
    top_refs = result.data["top_refs"]
    assert "top_ref_0" in top_refs
    assert "top_ref_1" in top_refs
    assert "active_index" in top_refs


def _make_realm_array_header(
    flags: int = 0x0E,
    size: int = 0,
) -> bytes:
    """Build an 8-byte Realm array header for tests."""
    return b"\x41\x41\x41\x41" + bytes([flags]) + size.to_bytes(3, "big")


def test_realm_array_header_decoding(tmp_path: Path) -> None:
    """_parse_array_header correctly decodes flags and computes payload size."""
    from crush.parsers.realm_parser import _parse_array_header

    # Example from PDF: flags=0x0E, size=5 → width_scheme=1, width=32 bytes → 160 bytes payload
    raw = _make_realm_array_header(flags=0x0E, size=5)
    hdr = _parse_array_header(raw, 0)
    assert hdr is not None
    assert hdr["is_inner_bptree_node"] is False
    assert hdr["has_refs"] is False
    assert hdr["width_scheme"] == 1
    assert hdr["width"] == 32
    assert hdr["Element count (size)"] == 5
    assert hdr["Payload bytes (raw)"] == 160   # 32 * 5
    assert hdr["Total array bytes"] == 168      # 8 header + 160

    # flags=0x46: has_refs=True, scheme=0, width=32 bits (4 bytes/elem), size=11 → 44 raw → 48 aligned
    raw2 = _make_realm_array_header(flags=0x46, size=11)
    hdr2 = _parse_array_header(raw2, 0)
    assert hdr2 is not None
    assert hdr2["has_refs"] is True
    assert hdr2["width_scheme"] == 0
    assert hdr2["width"] == 32
    assert hdr2["Element count (size)"] == 11
    assert hdr2["Payload bytes (raw)"] == 44    # ceil(32*11/8)
    assert hdr2["Payload bytes (aligned)"] == 48
    assert hdr2["Total array bytes"] == 56


def test_realm_schema_extraction(tmp_path: Path) -> None:
    """Schema extraction follows the B+ tree path and returns class names."""
    from crush.parsers.realm_parser import _parse_array_header, _extract_schema

    # Build a minimal realm file: file header + schema array + root ref array
    # Offsets (all computed to avoid overlap):
    #   0x00 (0):  24-byte file header  (top_ref1 → ROOT_OFFSET, flags=0x01)
    #   0x18 (24): schema data array    (flags=0x0E, size=2, width=32 bytes → 72 total)
    #   0x60 (96): root ref array       (flags=0x46, size=1, 4-byte ref → SCHEMA_OFFSET)

    SCHEMA_OFFSET = 24   # right after file header
    # schema array = 8-byte header + 2 × 32-byte entries = 72 bytes
    ROOT_OFFSET = SCHEMA_OFFSET + 72  # = 96

    # Two 32-byte schema entries
    entry0 = b"metadata\x00" + b"\x00" * 23
    entry1 = b"class_Task\x00" + b"\x00" * 21
    schema_hdr = b"\x41\x41\x41\x41\x0E" + (2).to_bytes(3, "big")  # flags=0x0E, size=2
    schema_array = schema_hdr + entry0 + entry1  # 8 + 32 + 32 = 72 bytes

    # Root ref array: flags=0x46, size=1, width_scheme=0, width=32bits → 4-byte LE ref
    # payload_bytes = ceil(32*1/8)=4, aligned=8
    root_hdr_bytes = b"\x41\x41\x41\x41\x46" + (1).to_bytes(3, "big")
    ref_payload = SCHEMA_OFFSET.to_bytes(4, "little") + b"\x00" * 4  # padded to 8
    root_array = root_hdr_bytes + ref_payload  # 16 bytes

    # File header: top_ref1=ROOT_OFFSET, flags=0x01 (top_ref1 active)
    file_hdr = (
        (0).to_bytes(8, "little")               # top_ref0 = 0 (unused)
        + ROOT_OFFSET.to_bytes(8, "little")     # top_ref1 = 96
        + b"T-DB"                               # mnemonic
        + bytes([24, 24, 0, 0x01])              # fmt0, fmt1, reserved, flags
    )

    realm_bytes = file_hdr + schema_array + root_array

    realm_path = tmp_path / "test.realm"
    realm_path.write_bytes(realm_bytes)

    vfs = DirectoryVFS(tmp_path)
    root = vfs.root()
    node = next(c for c in root.children if c.name == "test.realm")

    parser = RealmParser()
    result = parser.parse(node, vfs)

    assert result.viewer_type == "realm"
    schema = result.data["schema"]
    assert "metadata" in schema
    assert "class_Task" in schema
    assert result.metadata.get("Tables found") == "2"


def test_realm_blob_leaf_decoding() -> None:
    """_read_blob_leaf correctly extracts binary data using N+1 offsets."""
    from crush.parsers.realm_parser import _read_blob_leaf

    # Two blob values: b"\xDE\xAD" (2 bytes) and b"\xBE\xEF\xFF" (3 bytes).
    # Layout (all arrays stored sequentially from offset 0):
    #
    #   pos   0: offsets array  — 3 entries × 2 bytes (width=16, scheme=0)
    #                             values: 0, 2, 5  (LE)
    #                             header: AAAA + flags=0x05 + size=3 → payload=6 → aligned=8
    #                             total 16 bytes
    #   pos  16: blob data array — 5 raw bytes (scheme=2)
    #                             header: AAAA + flags=0x10 + size=5 → payload=5 → aligned=8
    #                             total 16 bytes
    #   pos  32: null bitmap    — 2 rows, all non-null (width=1, scheme=0)
    #                             header: AAAA + flags=0x01 + size=2 → payload=1 → aligned=8
    #                             total 16 bytes
    #   pos  48: col ref array  — 3 refs × 4 bytes (width=32, scheme=0)
    #                             header: AAAA + flags=0x46 + size=3 → payload=12 → aligned=16
    #                             total 24 bytes
    #   COL_OFFSET = 48

    OFFS_OFF = 0
    BLOB_OFF = 16
    NULL_OFF = 32
    COL_OFF = 48

    offs_hdr = b"\x41\x41\x41\x41\x05" + (3).to_bytes(3, "big")
    offs_payload = (0).to_bytes(2, "little") + (2).to_bytes(2, "little") + (5).to_bytes(2, "little") + b"\x00\x00"
    offs_array = offs_hdr + offs_payload  # 16 bytes

    blob_hdr = b"\x41\x41\x41\x41\x10" + (5).to_bytes(3, "big")
    blob_payload = b"\xDE\xAD\xBE\xEF\xFF" + b"\x00\x00\x00"
    blob_array = blob_hdr + blob_payload  # 16 bytes

    null_hdr = b"\x41\x41\x41\x41\x01" + (2).to_bytes(3, "big")
    null_payload = b"\x00" + b"\x00" * 7
    null_array = null_hdr + null_payload  # 16 bytes

    col_hdr = b"\x41\x41\x41\x41\x46" + (3).to_bytes(3, "big")
    col_payload = (
        OFFS_OFF.to_bytes(4, "little")
        + BLOB_OFF.to_bytes(4, "little")
        + NULL_OFF.to_bytes(4, "little")
        + b"\x00\x00\x00\x00"  # align to 16
    )
    col_array = col_hdr + col_payload  # 24 bytes

    raw = offs_array + blob_array + null_array + col_array

    result = _read_blob_leaf(raw, COL_OFF, len(raw), expected_rows=2)
    assert result is not None
    assert len(result) == 2
    assert result[0] == "<blob 2B: dead>"
    assert result[1] == "<blob 3B: beefff>"


def test_realm_string_leaf_rejects_blob_offsets() -> None:
    """_read_string_leaf returns None when offsets count != expected_rows (blob format)."""
    from crush.parsers.realm_parser import _read_string_leaf

    # Re-use the same blob layout from test_realm_blob_leaf_decoding.
    OFFS_OFF = 0
    BLOB_OFF = 16
    NULL_OFF = 32
    COL_OFF = 48

    offs_hdr = b"\x41\x41\x41\x41\x05" + (3).to_bytes(3, "big")
    offs_payload = (0).to_bytes(2, "little") + (2).to_bytes(2, "little") + (5).to_bytes(2, "little") + b"\x00\x00"
    blob_hdr = b"\x41\x41\x41\x41\x10" + (5).to_bytes(3, "big")
    blob_payload = b"\xDE\xAD\xBE\xEF\xFF" + b"\x00\x00\x00"
    null_hdr = b"\x41\x41\x41\x41\x01" + (2).to_bytes(3, "big")
    null_payload = b"\x00" + b"\x00" * 7
    col_hdr = b"\x41\x41\x41\x41\x46" + (3).to_bytes(3, "big")
    col_payload = (
        OFFS_OFF.to_bytes(4, "little") + BLOB_OFF.to_bytes(4, "little")
        + NULL_OFF.to_bytes(4, "little") + b"\x00\x00\x00\x00"
    )
    raw = (offs_hdr + offs_payload + blob_hdr + blob_payload
           + null_hdr + null_payload + col_hdr + col_payload)

    # With expected_rows=2, string reader must reject because offs_count(3) != 2
    result = _read_string_leaf(raw, COL_OFF, len(raw), expected_rows=2)
    assert result is None


def _u16(value: int) -> bytes:
    return bytes([(value >> 8) & 0xFF, value & 0xFF])


def _utf(s: str) -> bytes:
    data = s.encode("utf-8")
    return _u16(len(data)) + data


def _interned(s: str) -> bytes:
    return _u16(0xFFFF) + _utf(s)


def _make_abx_bytes() -> bytes:
    # Minimal ABX for: <root attr="value"/>
    magic = b"ABX\x00"
    start_doc = bytes([0x00])
    start_tag = bytes([0x22]) + _utf("root")  # TYPE_STRING + START_TAG
    attr = bytes([0x2F]) + _interned("attr") + _utf("value")  # ATTRIBUTE token
    end_tag = bytes([0x23]) + _utf("root")  # TYPE_STRING + END_TAG
    end_doc = bytes([0x01])
    return magic + start_doc + start_tag + attr + end_tag + end_doc


def test_abx_parser_parse(tmp_path: Path) -> None:
    abx_path = tmp_path / "binary.xml"
    abx_path.write_bytes(_make_abx_bytes())

    vfs = DirectoryVFS(tmp_path)
    root = vfs.root()
    node = next(c for c in root.children if c.name == "binary.xml")

    parser = AbxParser()
    assert parser.can_parse(node.path, vfs.peek(node))

    result = parser.parse(node, vfs)
    assert result.viewer_type == "abx"
    assert "<root" in result.data["xml_str"]
    assert "attr" in result.data["xml_str"]
    tree = result.data["tree"]
    assert tree["@tag"] == "root"
    assert tree["@attribs"]["attr"] == "value"


# ---------------------------------------------------------------------------
# HexFallbackParser — format identification via FormatDatabase
# ---------------------------------------------------------------------------

def test_hex_fallback_identifies_sqlite_format(tmp_path: Path) -> None:
    raw = b"SQLite format 3\x00" + b"\x00" * 512
    (tmp_path / "mystery.bin").write_bytes(raw)

    vfs = DirectoryVFS(tmp_path)
    root = vfs.root()
    node = next(c for c in root.children if c.name == "mystery.bin")

    parser = HexFallbackParser()
    result = parser.parse(node, vfs)

    assert result.viewer_type == "hex"
    assert "Format (identified)" in result.metadata
    assert "SQLite" in result.metadata["Format (identified)"]
    assert "Parser support" in result.metadata
    assert result.metadata["Parser support"] == "Supported"


def test_hex_fallback_unknown_has_no_format_key(tmp_path: Path) -> None:
    raw = b"\xDE\xAD\xBE\xEF" * 32
    (tmp_path / "random.xyz999").write_bytes(raw)

    vfs = DirectoryVFS(tmp_path)
    root = vfs.root()
    node = next(c for c in root.children if c.name == "random.xyz999")

    parser = HexFallbackParser()
    result = parser.parse(node, vfs)

    assert result.viewer_type == "hex"
    assert "Format (identified)" not in result.metadata


# ---------------------------------------------------------------------------
# _detect_encoding — text viewer encoding detection
# ---------------------------------------------------------------------------

def test_detect_utf8_bom() -> None:
    raw = b"\xef\xbb\xbf" + "hello".encode("utf-8")
    text, label = _detect_encoding(raw)
    assert text == "hello"
    assert label == "UTF-8 BOM"


def test_detect_utf16_le_bom() -> None:
    raw = b"\xff\xfe" + "hi".encode("utf-16-le")
    text, label = _detect_encoding(raw)
    assert text == "hi"
    assert label == "UTF-16 LE"


def test_detect_utf16_be_bom() -> None:
    raw = b"\xfe\xff" + "hi".encode("utf-16-be")
    text, label = _detect_encoding(raw)
    assert text == "hi"
    assert label == "UTF-16 BE"


def test_detect_plain_utf8() -> None:
    raw = "plain ascii".encode("utf-8")
    text, label = _detect_encoding(raw)
    assert text == "plain ascii"
    assert label == "UTF-8"


def test_detect_utf16_le_no_bom() -> None:
    # UTF-16 LE without BOM — non-ASCII chars put null bytes at odd positions
    # and make the raw bytes invalid as strict UTF-8, triggering the heuristic
    raw = "héllo wörld".encode("utf-16-le")
    text, label = _detect_encoding(raw)
    assert "h" in text
    assert "UTF-16 LE" in label


def test_detect_lossy_fallback() -> None:
    # Latin-1 bytes that are not valid UTF-8
    raw = b"\xff\xfe\xfd" * 10  # matches UTF-16 LE BOM — use something else
    # Use bytes that are invalid UTF-8 and won't trigger UTF-16 LE heuristic
    raw = bytes([0x80, 0x81, 0x82, 0x83] * 20)
    text, label = _detect_encoding(raw)
    assert isinstance(text, str)
    assert "lossy" in label.lower() or "UTF-8" in label
