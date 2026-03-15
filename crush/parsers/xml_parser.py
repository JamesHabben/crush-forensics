"""XML parser."""
from __future__ import annotations

from typing import Any

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import AbstractParser, ParseResult


class XmlParser(AbstractParser):
    SUPPORTED_EXTENSIONS = [".xml"]
    DISPLAY_NAME = "XML document"

    def can_parse(self, path: str, peek_bytes: bytes) -> bool:
        stripped = peek_bytes.lstrip()
        return stripped[:5] == b"<?xml" or stripped[:1] == b"<"

    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        from lxml import etree
        raw = vfs.read(node)
        try:
            root = etree.fromstring(raw)
            data = _element_to_dict(root)
            text = " ".join(str(t) for t in root.itertext())[:4000]
        except etree.XMLSyntaxError as exc:
            data = {"error": str(exc), "raw": raw[:500].decode("utf-8", errors="replace")}
            text = ""
        return ParseResult(
            viewer_type="tree",
            data=data,
            metadata={"File size": f"{node.size:,} B"},
            text_index=text,
        )


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
