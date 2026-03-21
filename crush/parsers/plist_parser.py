"""plist parser — handles both binary and XML plist files."""
from __future__ import annotations

from io import BytesIO
import plistlib
from typing import Any, cast

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import AbstractParser, ParseResult
from crush.third_party.ccl_bplist import (
    load as bplist_load,
    deserialise_NsKeyedArchiver,
    NSKeyedArchiver_common_objects_convertor,
    set_object_converter,
)

_BPLIST_MAGIC = b"bplist"
_XML_PLIST_SIG = b"<?xml"


class PlistParser(AbstractParser):
    SUPPORTED_EXTENSIONS = [".plist"]
    DISPLAY_NAME = "Property list (plist)"

    def can_parse(self, path: str, peek_bytes: bytes) -> bool:
        if peek_bytes[:6] == _BPLIST_MAGIC:
            return True
        if peek_bytes[:5] == _XML_PLIST_SIG:
            return _is_plist_xml(peek_bytes)
        return False

    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        raw = vfs.read(node)
        if raw[:6] == _BPLIST_MAGIC:
            fmt = "binary"
            _set_object_converter = cast(Any, set_object_converter)
            _bplist_load = cast(Any, bplist_load)
            _deserialize = cast(Any, deserialise_NsKeyedArchiver)
            _set_object_converter(NSKeyedArchiver_common_objects_convertor)
            data = _bplist_load(BytesIO(raw))
            if isinstance(data, dict) and data.get("$archiver") in ("NSKeyedArchiver", "NRKeyedArchiver"):
                try:
                    data = _deserialize(data)
                    fmt = "binary (NSKeyedArchiver)"
                except Exception:
                    pass
        else:
            fmt = "XML"
            data = plistlib.loads(raw)
        return ParseResult(
            viewer_type="tree",
            data=data,
            metadata={"Format": fmt, "File size": f"{node.size:,} B"},
            text_index=_flatten_text(data),
        )


def _flatten_text(obj: Any, max_chars: int = 4000) -> str:
    parts: list[str] = []
    _walk(obj, parts, max_chars)
    return " ".join(parts)


def _walk(obj: Any, parts: list[str], limit: int) -> None:
    if len(" ".join(parts)) >= limit:
        return
    if isinstance(obj, str):
        parts.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            parts.append(str(k))
            _walk(v, parts, limit)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _walk(item, parts, limit)


def _is_plist_xml(peek_bytes: bytes) -> bool:
    text = peek_bytes[:2048].decode("utf-8", errors="ignore")
    i = 0
    while True:
        lt = text.find("<", i)
        if lt == -1:
            return False
        if lt + 1 >= len(text):
            return False
        nxt = text[lt + 1]
        # Skip declarations, comments, and doctypes
        if nxt in ("?", "!"):
            gt = text.find(">", lt + 1)
            if gt == -1:
                return False
            i = gt + 1
            continue
        # Parse tag name
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
