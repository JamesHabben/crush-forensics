# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Crush Contributors
"""JSON parser — handles JSON documents."""
from __future__ import annotations

import json
from typing import Any

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import AbstractParser, ParseResult


class JsonParser(AbstractParser):
    SUPPORTED_EXTENSIONS = [".json", ".geojson"]
    DISPLAY_NAME = "JSON document"

    def can_parse(self, path: str, peek_bytes: bytes) -> bool:
        if any(path.lower().endswith(ext) for ext in self.SUPPORTED_EXTENSIONS):
            return True
        stripped = peek_bytes.lstrip()
        return stripped[:1] in (b"{", b"[")

    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        raw = vfs.read(node)
        try:
            text = raw.decode("utf-8")
        except Exception:
            text = raw.decode("utf-8", errors="replace")
        try:
            data = json.loads(text)
            meta = {"File size": f"{node.size:,} B", "Format": "JSON"}
            return ParseResult(
                viewer_type="tree",
                data=data,
                metadata=meta,
                text_index=_flatten_text(data),
            )
        except json.JSONDecodeError as exc:
            data = {"error": str(exc), "raw": text[:500]}
            return ParseResult(
                viewer_type="tree",
                data=data,
                metadata={"File size": f"{node.size:,} B", "Format": "JSON (parse error)"},
                text_index="",
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
