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
