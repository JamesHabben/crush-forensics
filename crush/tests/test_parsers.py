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
