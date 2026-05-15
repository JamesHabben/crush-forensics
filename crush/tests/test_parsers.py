# SPDX-License-Identifier: Apache-2.0
"""Tests for built-in parsers."""
from __future__ import annotations

import plistlib
import sqlite3
import struct
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
    assert result[0] == ("<blob 2B: dead>", b"\xde\xad")
    assert result[1] == ("<blob 3B: beefff>", b"\xbe\xef\xff")


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


# ---------------------------------------------------------------------------
# LevelDB parser
# ---------------------------------------------------------------------------

def _varint(n: int) -> bytes:
    out = []
    while n > 127:
        out.append((n & 0x7f) | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def _make_log_entry(key: bytes, value: bytes | None, seq: int) -> bytes:
    """Build one LevelDB log record (Full type). CRC is zeroed — ccl_leveldb doesn't validate it."""
    batch = struct.pack("<QI", seq, 1)
    if value is not None:
        batch += b"\x01" + _varint(len(key)) + key + _varint(len(value)) + value
    else:
        batch += b"\x00" + _varint(len(key)) + key
    header = struct.pack("<IHB", 0, len(batch), 1)  # CRC=0, length, type=Full
    return header + batch


def _make_minimal_leveldb(
    path: Path,
    records: list[tuple[bytes, bytes | None]],
) -> None:
    """Write a minimal LevelDB directory with one log file containing *records*."""
    path.mkdir(parents=True, exist_ok=True)
    log_data = b"".join(
        _make_log_entry(k, v, seq=i + 1) for i, (k, v) in enumerate(records)
    )
    (path / "000001.log").write_bytes(log_data)
    (path / "MANIFEST-000001").write_bytes(b"")  # empty manifest — parser handles gracefully


def test_leveldb_can_parse_dir_ldb(tmp_path: Path) -> None:
    (tmp_path / "000001.ldb").touch()
    from crush.parsers.leveldb_parser import LeveldbParser
    node = DirectoryVFS(tmp_path).root()
    assert LeveldbParser().can_parse_dir(node)


def test_leveldb_can_parse_dir_log(tmp_path: Path) -> None:
    (tmp_path / "000001.log").touch()
    from crush.parsers.leveldb_parser import LeveldbParser
    node = DirectoryVFS(tmp_path).root()
    assert LeveldbParser().can_parse_dir(node)


def test_leveldb_can_parse_dir_sst(tmp_path: Path) -> None:
    (tmp_path / "000001.sst").touch()
    from crush.parsers.leveldb_parser import LeveldbParser
    node = DirectoryVFS(tmp_path).root()
    assert LeveldbParser().can_parse_dir(node)


def test_leveldb_can_parse_dir_manifest(tmp_path: Path) -> None:
    (tmp_path / "MANIFEST-000001").touch()
    from crush.parsers.leveldb_parser import LeveldbParser
    node = DirectoryVFS(tmp_path).root()
    assert LeveldbParser().can_parse_dir(node)


def test_leveldb_can_parse_dir_negative(tmp_path: Path) -> None:
    (tmp_path / "README.txt").write_text("not a leveldb")
    from crush.parsers.leveldb_parser import LeveldbParser
    node = DirectoryVFS(tmp_path).root()
    assert not LeveldbParser().can_parse_dir(node)


def test_leveldb_parse_viewer_type(tmp_path: Path) -> None:
    db = tmp_path / "testdb"
    _make_minimal_leveldb(db, [(b"key1", b"value1")])
    from crush.parsers.leveldb_parser import LeveldbParser
    vfs = DirectoryVFS(tmp_path)
    node = next(c for c in vfs.root().children if c.name == "testdb")
    result = LeveldbParser().parse(node, vfs)
    assert result.viewer_type == "leveldb"


def test_leveldb_parse_live_records(tmp_path: Path) -> None:
    db = tmp_path / "testdb"
    _make_minimal_leveldb(db, [(b"hello", b"world")])
    from crush.parsers.leveldb_parser import LeveldbParser
    vfs = DirectoryVFS(tmp_path)
    node = next(c for c in vfs.root().children if c.name == "testdb")
    result = LeveldbParser().parse(node, vfs)
    records = result.data["records"]
    live = [r for r in records if r["state"] == "Live"]
    assert len(live) == 1
    assert live[0]["user_key_bytes"] == b"hello"
    assert live[0]["value_bytes"] == b"world"
    assert live[0]["user_key_text"] == "hello"
    assert live[0]["value_text"] == "world"


def test_leveldb_parse_deleted_records(tmp_path: Path) -> None:
    db = tmp_path / "testdb"
    _make_minimal_leveldb(db, [(b"gone", b"data"), (b"gone", None)])
    from crush.parsers.leveldb_parser import LeveldbParser
    vfs = DirectoryVFS(tmp_path)
    node = next(c for c in vfs.root().children if c.name == "testdb")
    result = LeveldbParser().parse(node, vfs)
    records = result.data["records"]
    deleted = [r for r in records if r["state"] == "Deleted"]
    assert len(deleted) >= 1
    assert deleted[0]["user_key_bytes"] == b"gone"


def test_leveldb_parse_file_stats(tmp_path: Path) -> None:
    db = tmp_path / "testdb"
    _make_minimal_leveldb(db, [(b"k", b"v"), (b"k2", None)])
    from crush.parsers.leveldb_parser import LeveldbParser
    vfs = DirectoryVFS(tmp_path)
    node = next(c for c in vfs.root().children if c.name == "testdb")
    result = LeveldbParser().parse(node, vfs)
    files = result.data["files"]
    assert len(files) == 1
    assert files[0]["type"] == "Log"
    assert files[0]["total"] == 2
    assert files[0]["live"] == 1
    assert files[0]["deleted"] == 1


def test_leveldb_binary_key_value(tmp_path: Path) -> None:
    db = tmp_path / "testdb"
    binary_key = b"\x80\x81\x82\x83"   # invalid UTF-8 (continuation bytes without leader)
    binary_val = b"\xff\xfe\xfd"
    _make_minimal_leveldb(db, [(binary_key, binary_val)])
    from crush.parsers.leveldb_parser import LeveldbParser
    vfs = DirectoryVFS(tmp_path)
    node = next(c for c in vfs.root().children if c.name == "testdb")
    result = LeveldbParser().parse(node, vfs)
    records = result.data["records"]
    assert records[0]["user_key_bytes"] == binary_key
    assert records[0]["value_bytes"] == binary_val
    assert records[0]["user_key_text"] is None   # not valid UTF-8
    assert records[0]["value_text"] is None


def test_leveldb_parse_record_has_offset(tmp_path: Path) -> None:
    db = tmp_path / "testdb"
    _make_minimal_leveldb(db, [(b"key1", b"value1")])
    from crush.parsers.leveldb_parser import LeveldbParser
    vfs = DirectoryVFS(tmp_path)
    node = next(c for c in vfs.root().children if c.name == "testdb")
    result = LeveldbParser().parse(node, vfs)
    records = result.data["records"]
    assert len(records) >= 1
    assert "offset" in records[0]
    assert isinstance(records[0]["offset"], int)
    assert records[0]["offset"] >= 0


# ---------------------------------------------------------------------------
# BlobInspector helpers: _is_image, _render_protobuf
# ---------------------------------------------------------------------------

def test_is_image_png() -> None:
    from crush.viewers.table_viewer import _is_image
    assert _is_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)


def test_is_image_jpeg() -> None:
    from crush.viewers.table_viewer import _is_image
    assert _is_image(b"\xff\xd8\xff\xe0" + b"\x00" * 100)


def test_is_image_gif87() -> None:
    from crush.viewers.table_viewer import _is_image
    assert _is_image(b"GIF87a" + b"\x00" * 100)


def test_is_image_gif89() -> None:
    from crush.viewers.table_viewer import _is_image
    assert _is_image(b"GIF89a" + b"\x00" * 100)


def test_is_image_negative() -> None:
    from crush.viewers.table_viewer import _is_image
    assert not _is_image(b"SQLite format 3\x00" + b"\x00" * 100)
    assert not _is_image(b"")
    assert not _is_image(b"\x00\x01\x02\x03")


def test_render_protobuf_simple() -> None:
    from crush.viewers.table_viewer import _render_protobuf
    entries = [
        {"field": 1, "wire_type": "varint", "value": 42},
        {"field": 2, "wire_type": "varint", "value": 0},
    ]
    result = _render_protobuf(entries)
    assert "1 [varint]: 42" in result
    assert "2 [varint]: 0" in result


def test_render_protobuf_nested() -> None:
    from crush.viewers.table_viewer import _render_protobuf
    entries = [
        {"field": 1, "wire_type": "message", "value": {
            "entries": [{"field": 3, "wire_type": "varint", "value": 99}]
        }},
    ]
    result = _render_protobuf(entries)
    assert "1 {" in result
    assert "3 [varint]: 99" in result
    assert "}" in result


def test_render_protobuf_bytes_value() -> None:
    from crush.viewers.table_viewer import _render_protobuf
    entries = [{"field": 2, "wire_type": "bytes", "value": bytes(range(40))}]
    result = _render_protobuf(entries)
    assert "2:" in result           # field number present
    assert "…" in result            # truncation marker for > 32 bytes
    assert "00010203" in result     # hex content starts correctly


# ---------------------------------------------------------------------------
# SEGB protobuf decoder tests
# ---------------------------------------------------------------------------

def _varint(v: int) -> bytes:
    """Encode a single unsigned varint."""
    out = []
    while v > 127:
        out.append((v & 0x7F) | 0x80)
        v >>= 7
    out.append(v)
    return bytes(out)


def _proto_field(field_num: int, wire_type: int, payload: bytes) -> bytes:
    return _varint((field_num << 3) | wire_type) + payload


def test_parse_protobuf_varint_field() -> None:
    """Basic varint field is decoded correctly."""
    from crush.parsers.segb_parser import _parse_protobuf
    data = _proto_field(2, 0, _varint(42))
    result = _parse_protobuf(data)
    assert result[2] == 42


def test_parse_protobuf_string_field() -> None:
    """Length-delimited UTF-8 field is decoded as str."""
    from crush.parsers.segb_parser import _parse_protobuf
    s = b"com.apple.Preferences"
    data = _proto_field(2, 2, _varint(len(s)) + s)
    result = _parse_protobuf(data)
    assert result[2] == "com.apple.Preferences"


def test_parse_protobuf_repeated_fields() -> None:
    """Same field number appearing twice is collected into a list."""
    from crush.parsers.segb_parser import _parse_protobuf
    data = _proto_field(1, 0, _varint(10)) + _proto_field(1, 0, _varint(20))
    result = _parse_protobuf(data)
    assert result[1] == [10, 20]


def test_parse_protobuf_high_field_number() -> None:
    """Field numbers above 200 (old hard limit) are now parsed correctly."""
    from crush.parsers.segb_parser import _parse_protobuf
    data = _proto_field(750, 0, _varint(99))
    result = _parse_protobuf(data)
    assert 750 in result
    assert result[750] == 99


def test_parse_protobuf_multiple_fields() -> None:
    """Multiple different field numbers are all decoded."""
    from crush.parsers.segb_parser import _parse_protobuf
    s = b"hello"
    data = (
        _proto_field(1, 0, _varint(7))
        + _proto_field(2, 2, _varint(len(s)) + s)
        + _proto_field(300, 0, _varint(1))
    )
    result = _parse_protobuf(data)
    assert result[1] == 7
    assert result[2] == "hello"
    assert result[300] == 1


def test_proto_to_json_basic() -> None:
    """Simple protobuf payload serialises to valid JSON."""
    import json
    from crush.parsers.segb_parser import _proto_to_json
    s = b"com.apple.test"
    data = _proto_field(2, 2, _varint(len(s)) + s)
    j = _proto_to_json(data)
    obj = json.loads(j)
    assert obj["2"] == "com.apple.test"


def test_proto_to_json_repeated_fields_become_array() -> None:
    """Repeated fields are stored as JSON arrays."""
    import json
    from crush.parsers.segb_parser import _proto_to_json
    data = _proto_field(1, 0, _varint(10)) + _proto_field(1, 0, _varint(20))
    obj = json.loads(_proto_to_json(data))
    assert obj["1"] == [10, 20]


def test_proto_to_json_always_valid_json() -> None:
    """Garbage input always returns valid (empty) JSON, never raises."""
    import json
    from crush.parsers.segb_parser import _proto_to_json
    for bad in (b"", b"\xff\xff\xff", b"\x00" * 20):
        result = _proto_to_json(bad)
        obj = json.loads(result)   # must not raise
        assert isinstance(obj, dict)


def test_render_proto_payload_skips_undecodable_blobs() -> None:
    """Binary blobs that cannot be sub-parsed are omitted from display."""
    from crush.parsers.segb_parser import _render_proto_payload
    binary = b"\xde\xad\xbe\xef"
    data = _proto_field(5, 2, _varint(len(binary)) + binary)
    result = _render_proto_payload(data)
    # field 5 should be absent (undecodable blob → None → skipped)
    assert "5" not in result


def test_render_proto_payload_repeated_fields() -> None:
    """Repeated fields appear in the rendered output."""
    from crush.parsers.segb_parser import _render_proto_payload
    data = _proto_field(3, 0, _varint(1)) + _proto_field(3, 0, _varint(2))
    result = _render_proto_payload(data)
    assert result  # non-empty
    assert "3" in result


def test_create_segb_sqlite_payload_columns() -> None:
    """SQLite DB has both Payload (rendered text) and Payload JSON columns."""
    import json
    import sqlite3
    from crush.parsers.segb_parser import _create_segb_sqlite, _COLUMNS_V1
    s = b"com.apple.test"
    raw = _proto_field(2, 2, _varint(len(s)) + s)
    rendered = "2: \"com.apple.test\""
    rows = [
        [0, 0, "Current", "2024-01-01", "2024-01-01", 0, 0, True,
         len(raw), "com.apple.test", "", "", (rendered, raw)],
    ]
    path = _create_segb_sqlite(_COLUMNS_V1, rows)
    assert path is not None
    conn = sqlite3.connect(str(path))
    cols = [r[1] for r in conn.execute('PRAGMA table_info("SEGB")').fetchall()]
    assert "Payload" in cols
    assert "Payload JSON" in cols
    payload_val = conn.execute('SELECT "Payload" FROM SEGB').fetchone()[0]
    assert payload_val == rendered
    payload_json = conn.execute('SELECT "Payload JSON" FROM SEGB').fetchone()[0]
    obj = json.loads(payload_json)
    assert obj.get("2") == "com.apple.test"
    conn.close()
    path.unlink(missing_ok=True)
