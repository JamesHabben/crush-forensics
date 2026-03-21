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
        if not (stripped[:5] == b"<?xml" or stripped[:1] == b"<"):
            return False
        if path.lower().endswith(".plist"):
            return False
        return not _looks_like_plist_xml(peek_bytes)

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
    children: list[dict[str, Any]] = []
    map_entries: dict[str, list[Any]] = {}
    for child in el:
        child_dict = _element_to_dict(child)
        children.append(child_dict)

        name_attr = _get_attrib(child, "name")
        if name_attr is not None:
            value: Any | None = _get_attrib(child, "value")
            if value is None:
                if child.text and child.text.strip():
                    value = child.text.strip()
                elif len(child):
                    value = child_dict
                else:
                    value = ""
            map_entries.setdefault(name_attr, []).append(value)

    if children:
        result["@children"] = children
    if map_entries:
        normalized_map = {
            key: values[0] if len(values) == 1 else values
            for key, values in map_entries.items()
        }
        # For Android-style <map>, show entries directly at the root
        # so users don't have to drill into @children/@map to see values.
        if _local_tag(el) == "map":
            result.update(normalized_map)
        else:
            result["@map"] = normalized_map
    return result


def _looks_like_plist_xml(peek_bytes: bytes) -> bool:
    text = peek_bytes[:2048].decode("utf-8", errors="ignore")
    i = 0
    while True:
        lt = text.find("<", i)
        if lt == -1:
            return False
        if lt + 1 >= len(text):
            return False
        nxt = text[lt + 1]
        if nxt in ("?", "!"):
            gt = text.find(">", lt + 1)
            if gt == -1:
                return False
            i = gt + 1
            continue
        j = lt + 1
        name_chars: list[str] = []
        while j < len(text):
            ch = text[j]
            if ch.isspace() or ch in (">", "/"):
                break
            name_chars.append(ch)
            j += 1
        if not name_chars:
            return False
        tag = "".join(name_chars).split(":")[-1].lower()
        return tag == "plist"


def _local_tag(el: Any) -> str:
    tag = str(getattr(el, "tag", ""))
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _get_attrib(el: Any, name: str) -> str | None:
    for key, value in getattr(el, "attrib", {}).items():
        if key == name or key.endswith(f"}}{name}"):
            return value
    return None
