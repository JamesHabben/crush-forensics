# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Crush Contributors
"""ABX (Android Binary XML) parser.

Uses the best-effort decoder in `abx_decoder` to reconstruct XML, then
parses that XML into a nested dict for the tree viewer.
"""
from __future__ import annotations

from typing import Any

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import AbstractParser, ParseResult
from crush.parsers.abx_decoder import decode_abx

_MAGIC = b"ABX\x00"


class AbxParser(AbstractParser):
    SUPPORTED_EXTENSIONS = [".xml"]   # ABX files keep the .xml extension on Android
    DISPLAY_NAME = "Android Binary XML (ABX)"

    def can_parse(self, path: str, peek_bytes: bytes) -> bool:
        return peek_bytes[:4] == _MAGIC

    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        raw = vfs.read(node)
        try:
            decoded = decode_abx(raw)
            xml_str = decoded.xml
            try:
                tree = _xml_to_tree(xml_str)
            except Exception as exc:
                tree = {
                    "error": str(exc),
                    "hint": "XML reconstruction failed; see right pane",
                }
            meta: dict[str, Any] = {
                "Format": "Android Binary XML (ABX)",
                "File size": f"{node.size:,} B",
            }
            if decoded.warnings:
                meta["Warnings"] = "; ".join(decoded.warnings[:3])
            return ParseResult(
                viewer_type="abx",
                data={"tree": tree, "xml_str": xml_str},
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


def _xml_to_tree(xml_str: str) -> dict[str, Any]:
    """Convert XML string to nested dict for the tree viewer."""
    from lxml import etree

    root = etree.fromstring(xml_str.encode("utf-8", errors="replace"))
    return _element_to_dict(root)


def _element_to_dict(el: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"@tag": str(el.tag)}
    if el.attrib:
        result["@attribs"] = dict(el.attrib)
    if el.text and el.text.strip():
        result["@text"] = el.text.strip()
    children = [_element_to_dict(child) for child in el]
    if children:
        result["@children"] = children
    return result
