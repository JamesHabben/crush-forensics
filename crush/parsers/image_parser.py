# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Crush Contributors
"""Image parser — routes image files to the image viewer."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import AbstractParser, ParseResult


class ImageParser(AbstractParser):
    SUPPORTED_EXTENSIONS = [
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
        ".tif", ".tiff", ".heic", ".heif",
    ]
    DISPLAY_NAME = "Image"

    def can_parse(self, path: str, peek_bytes: bytes) -> bool:
        ext = Path(path).suffix.lower()
        if ext in self.SUPPORTED_EXTENSIONS:
            return True
        return _looks_like_image(peek_bytes)

    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        raw = vfs.read(node)
        meta: dict[str, Any] = {
            "Format": "Image",
            "File size": f"{node.size:,} B",
        }
        return ParseResult(viewer_type="image", data=raw, metadata=meta)


def _looks_like_image(peek: bytes) -> bool:
    if len(peek) < 4:
        return False
    if peek.startswith(b"\xFF\xD8\xFF"):
        return True  # JPEG
    if peek.startswith(b"\x89PNG\r\n\x1a\n"):
        return True  # PNG
    if peek.startswith(b"GIF87a") or peek.startswith(b"GIF89a"):
        return True  # GIF
    if peek.startswith(b"BM"):
        return True  # BMP
    if peek.startswith(b"II*\x00") or peek.startswith(b"MM\x00*"):
        return True  # TIFF
    if len(peek) >= 12 and peek.startswith(b"RIFF") and peek[8:12] == b"WEBP":
        return True  # WebP
    if len(peek) >= 12 and peek[4:8] == b"ftyp":
        brand = peek[8:12]
        if brand in {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}:
            return True  # HEIC/HEIF family
    return False
