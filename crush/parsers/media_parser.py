# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Media parser — routes audio/video files to the media viewer."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import AbstractParser, ParseResult


class MediaParser(AbstractParser):
    SUPPORTED_EXTENSIONS = [
        # Audio
        ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".amr",
        # Video
        ".mp4", ".m4v", ".mov", ".mkv", ".avi", ".webm", ".3gp", ".3g2",
    ]
    DISPLAY_NAME = "Media (Audio/Video)"

    def can_parse(self, path: str, peek_bytes: bytes) -> bool:  # noqa: ARG002
        ext = Path(path).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        raw = vfs.read(node)
        meta: dict[str, Any] = {
            "Format": "Media",
            "File size": f"{node.size:,} B",
        }
        return ParseResult(viewer_type="media", data=raw, metadata=meta)
