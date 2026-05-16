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
        try:
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
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Plist parse error for %s: %s", node.path, exc)
            try:
                raw_bytes = vfs.read(node)
            except Exception:
                raw_bytes = b""
            return ParseResult(
                viewer_type="hex",
                data=raw_bytes,
                metadata={
                    "Parse error": str(exc),
                    "Format": "plist (parse failed)",
                    "File size": f"{node.size:,} B",
                },
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
    return "<plist" in text.lower()
