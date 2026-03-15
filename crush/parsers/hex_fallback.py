"""Hex fallback — catches anything unrecognised and shows raw bytes."""
from __future__ import annotations

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import AbstractParser, ParseResult


class HexFallbackParser(AbstractParser):
    DISPLAY_NAME = "Hex viewer (fallback)"

    def can_parse(self, path: str, peek_bytes: bytes) -> bool:
        return True  # Always matches — must be registered last

    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        raw = vfs.read(node)
        return ParseResult(
            viewer_type="hex",
            data=raw,
            metadata={
                "File size": f"{node.size:,} B",
                "Extension": node.extension or "(none)",
            },
        )
