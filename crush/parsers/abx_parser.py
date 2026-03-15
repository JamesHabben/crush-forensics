# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Crush Contributors
"""ABX (Android Binary XML) parser.

Format reference:
  https://www.cclsolutionsgroup.com/post/android-abx-binary-xml
  https://cs.android.com/android/platform/superproject/+/master:frameworks/base/
         core/java/com/android/internal/util/BinaryXmlSerializer.java

Structure:
  - 4-byte magic: b'ABX\\x00'
  - Sequence of tokens, each starting with a 1-byte event header:
      lower nibble = XML event type
      upper nibble = data type for the token's payload

XML event types (lower nibble):
  0x00  START_DOCUMENT
  0x01  END_DOCUMENT
  0x02  START_TAG
  0x03  END_TAG
  0x04  TEXT
  0x05  ATTRIBUTE

Data types (upper nibble):
  0x00  TYPE_NULL
  0x10  TYPE_STRING          2-byte length-prefixed UTF-8 string
  0x20  TYPE_STRING_INTERNED 2-byte intern ID (string already seen in this file)
  0x30  TYPE_BYTES_HEX       2-byte length + raw bytes (shown as hex)
  0x40  TYPE_BYTES_BASE64    2-byte length + raw bytes (shown as base64)
  0x50  TYPE_INT             4-byte big-endian signed int
  0x60  TYPE_INT_HEX         4-byte big-endian unsigned int (shown as 0x...)
  0x70  TYPE_LONG            8-byte big-endian signed long
  0x80  TYPE_LONG_HEX        8-byte big-endian unsigned long (shown as 0x...)
  0x90  TYPE_FLOAT           4-byte IEEE 754 float
  0xa0  TYPE_DOUBLE          8-byte IEEE 754 double
  0xb0  TYPE_BOOLEAN_TRUE    no payload
  0xc0  TYPE_BOOLEAN_FALSE   no payload
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import AbstractParser, ParseResult

_MAGIC = b"ABX\x00"

# --- Event type constants (lower nibble) ---
_EV_START_DOCUMENT = 0x00
_EV_END_DOCUMENT   = 0x01
_EV_START_TAG      = 0x02
_EV_END_TAG        = 0x03
_EV_TEXT           = 0x04
_EV_ATTRIBUTE      = 0x05

# --- Data type constants (upper nibble) ---
_DT_NULL            = 0x00
_DT_STRING          = 0x10
_DT_STRING_INTERNED = 0x20
_DT_BYTES_HEX       = 0x30
_DT_BYTES_BASE64    = 0x40
_DT_INT             = 0x50
_DT_INT_HEX         = 0x60
_DT_LONG            = 0x70
_DT_LONG_HEX        = 0x80
_DT_FLOAT           = 0x90
_DT_DOUBLE          = 0xa0
_DT_BOOLEAN_TRUE    = 0xb0
_DT_BOOLEAN_FALSE   = 0xc0


@dataclass
class AbxNode:
    """A node in the parsed ABX tree."""
    tag: str
    text: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    children: list["AbxNode"] = field(default_factory=list)


class AbxParser(AbstractParser):
    SUPPORTED_EXTENSIONS = [".xml"]   # ABX files keep the .xml extension on Android
    DISPLAY_NAME = "Android Binary XML (ABX)"

    def can_parse(self, path: str, peek_bytes: bytes) -> bool:
        return peek_bytes[:4] == _MAGIC

    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        raw = vfs.read(node)
        try:
            tree, xml_str = _decode_abx(raw)
            meta: dict[str, Any] = {
                "Format": "Android Binary XML (ABX)",
                "File size": f"{node.size:,} B",
            }
            return ParseResult(
                viewer_type="abx",
                data={"tree": _node_to_dict(tree), "xml_str": xml_str},
                metadata=meta,
                text_index=xml_str[:4000],
            )
        except Exception as exc:
            # Fallback: show error in tree viewer
            return ParseResult(
                viewer_type="tree",
                data={"error": str(exc), "hint": "File may be a newer ABX version"},
                metadata={"Format": "ABX (parse error)", "File size": f"{node.size:,} B"},
            )


# ---------------------------------------------------------------------------
# Core decoder
# ---------------------------------------------------------------------------

_INTERN_NEW = 0xFFFF  # sentinel: string not yet seen, followed by length + UTF-8 bytes


def _decode_abx(data: bytes) -> tuple[AbxNode, str]:
    """Decode an ABX byte stream into an AbxNode tree and a reconstructed XML string.

    Interned string encoding (CCL / AOSP spec):
      - 2-byte unsigned short read first
      - If value == 0xFFFF: new string — read 2-byte length + UTF-8 bytes,
        assign next available ID
      - Otherwise: back-reference ID — look up in intern table
    """
    if data[:4] != _MAGIC:
        raise ValueError(f"Not an ABX file (magic={data[:4]!r})")

    pos = 4
    interned: list[str] = []   # intern table: index → string
    stack: list[AbxNode] = []  # open element stack
    root: AbxNode | None = None
    xml_lines: list[str] = []

    def read_bytes(n: int) -> bytes:
        nonlocal pos
        chunk = data[pos : pos + n]
        if len(chunk) < n:
            raise ValueError(f"Unexpected EOF at offset {pos} (wanted {n} B)")
        pos += n
        return chunk

    def read_interned() -> str:
        """Read an interned string: 0xFFFF+len+bytes for new, or id for known."""
        idx = struct.unpack(">H", read_bytes(2))[0]
        if idx == _INTERN_NEW:
            length = struct.unpack(">H", read_bytes(2))[0]
            s = read_bytes(length).decode("utf-8", errors="replace")
            interned.append(s)
            return s
        if idx < len(interned):
            return interned[idx]
        raise ValueError(f"Interned string id {idx} out of range (table size {len(interned)})")

    def read_value(data_type: int) -> str:
        """Decode a typed value payload according to the upper-nibble data type."""
        if data_type == _DT_NULL:
            return ""
        if data_type == _DT_STRING:
            length = struct.unpack(">H", read_bytes(2))[0]
            return read_bytes(length).decode("utf-8", errors="replace")
        if data_type == _DT_STRING_INTERNED:
            return read_interned()
        if data_type == _DT_BYTES_HEX:
            length = struct.unpack(">H", read_bytes(2))[0]
            return read_bytes(length).hex()
        if data_type == _DT_BYTES_BASE64:
            import base64
            length = struct.unpack(">H", read_bytes(2))[0]
            return base64.b64encode(read_bytes(length)).decode()
        if data_type == _DT_INT:
            return str(struct.unpack(">i", read_bytes(4))[0])
        if data_type == _DT_INT_HEX:
            return hex(struct.unpack(">I", read_bytes(4))[0])
        if data_type == _DT_LONG:
            return str(struct.unpack(">q", read_bytes(8))[0])
        if data_type == _DT_LONG_HEX:
            return hex(struct.unpack(">Q", read_bytes(8))[0])
        if data_type == _DT_FLOAT:
            return str(struct.unpack(">f", read_bytes(4))[0])
        if data_type == _DT_DOUBLE:
            return str(struct.unpack(">d", read_bytes(8))[0])
        if data_type == _DT_BOOLEAN_TRUE:
            return "true"
        if data_type == _DT_BOOLEAN_FALSE:
            return "false"
        raise ValueError(f"Unknown data type: 0x{data_type:02x}")

    xml_lines.append('<?xml version="1.0" encoding="utf-8"?>')

    while pos < len(data):
        header = data[pos]
        pos += 1
        event_type = header & 0x0F
        data_type  = header & 0xF0

        if event_type == _EV_START_DOCUMENT:
            pass

        elif event_type == _EV_END_DOCUMENT:
            break

        elif event_type == _EV_START_TAG:
            # data_type upper nibble is unused for START_TAG — name is always interned
            tag = read_interned()
            node_obj = AbxNode(tag=tag)
            if stack:
                stack[-1].children.append(node_obj)
            else:
                root = node_obj
            stack.append(node_obj)
            xml_lines.append(f"{'  ' * (len(stack) - 1)}<{tag}")

        elif event_type == _EV_END_TAG:
            # Consume the closing tag name (always interned, discard)
            read_interned()
            if stack:
                closed = stack.pop()
                indent = "  " * len(stack)
                if not closed.children and not closed.text:
                    xml_lines.append(f"{indent}/>")
                else:
                    xml_lines.append(f"{indent}</{closed.tag}>")

        elif event_type == _EV_TEXT:
            text = read_value(data_type)
            if stack:
                stack[-1].text = text
            xml_lines.append(f"{'  ' * len(stack)}{text}")

        elif event_type == _EV_ATTRIBUTE:
            # Header upper nibble = VALUE data type
            # After the header: interned name, then typed value
            attr_name  = read_interned()
            attr_value = read_value(data_type)
            if stack:
                stack[-1].attributes[attr_name] = attr_value
            xml_lines.append(f"{'  ' * len(stack)}  @{attr_name}={attr_value!r}")

        else:
            raise ValueError(f"Unknown event type 0x{event_type:02x} at offset {pos - 1}")

    if root is None:
        root = AbxNode(tag="(empty)")

    return root, "\n".join(xml_lines)


def _node_to_dict(node: AbxNode) -> dict[str, Any]:
    """Convert an AbxNode tree to a nested dict for the tree viewer."""
    result: dict[str, Any] = {}
    if node.attributes:
        result["@attributes"] = node.attributes
    if node.text.strip():
        result["@text"] = node.text
    for child in node.children:
        child_dict = _node_to_dict(child)
        if child.tag in result:
            existing = result[child.tag]
            if isinstance(existing, list):
                existing.append(child_dict)
            else:
                result[child.tag] = [existing, child_dict]
        else:
            result[child.tag] = child_dict
    return {node.tag: result}