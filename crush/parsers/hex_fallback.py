"""Hex fallback — catches anything unrecognised and shows raw bytes."""
from __future__ import annotations

from typing import Any

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import AbstractParser, ParseResult


class HexFallbackParser(AbstractParser):
    DISPLAY_NAME = "Hex viewer (fallback)"

    def can_parse(self, path: str, peek_bytes: bytes) -> bool:
        return True  # Always matches — must be registered last

    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        try:
            raw = vfs.read(node)
        except Exception as exc:
            return ParseResult(
                viewer_type="hex",
                data=b"",
                metadata={
                    "Read error": str(exc),
                    "File size": f"{node.size:,} B",
                    "Extension": node.extension or "(none)",
                },
            )

        meta: dict[str, Any] = {
            "File size": f"{node.size:,} B",
            "Extension": node.extension or "(none)",
        }

        # Identify the format even though we can't parse it
        try:
            from crush.core.format_db import FormatDatabase
            fmt = FormatDatabase.get().identify(raw[:512], node.name)
            if fmt:
                meta["Format (identified)"] = fmt.name
                if fmt.category:
                    meta["Category"] = fmt.category
                if fmt.platforms:
                    meta["Platforms"] = fmt.platforms.replace(",", ", ")
                if fmt.forensic_relevance:
                    meta["Forensic relevance"] = fmt.forensic_relevance
                if fmt.links:
                    meta["Reference"] = fmt.links[0][1]
                meta["Parser support"] = "Supported" if fmt.parser_class else "Not yet supported"
        except Exception:
            pass

        return ParseResult(viewer_type="hex", data=raw, metadata=meta)
