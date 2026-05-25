# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Image parser — routes image files to the image viewer."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import AbstractParser, ParseResult

# ISOBMFF brands that identify HEIF/HEIC/AVIF containers
_ISOBMFF_IMAGE_BRANDS: frozenset[bytes] = frozenset({
    b"heic", b"heix", b"hevc", b"hevx",  # HEIC (HEVC-based)
    b"heim", b"heis", b"hevm", b"hevs",  # HEIF multi-picture / tiled
    b"mif1", b"msf1",                    # HEIF (generic)
    b"avif", b"avis",                    # AVIF
})

# JPEG XL ISOBMFF container signature (12 bytes)
_JXL_CONTAINER_SIG = b"\x00\x00\x00\x0C\x4A\x58\x4C\x20\x0D\x0A\x87\x0A"


class ImageParser(AbstractParser):
    SUPPORTED_EXTENSIONS = [
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
        ".tif", ".tiff",
        ".heic", ".heif", ".avif",
        ".jxl",
    ]
    DISPLAY_NAME = "Image"

    def can_parse(self, path: str, peek_bytes: bytes) -> bool:
        ext = Path(path).suffix.lower()
        if ext in self.SUPPORTED_EXTENSIONS:
            return True
        return _looks_like_image(peek_bytes)

    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        raw = vfs.read(node)
        ext = Path(node.path).suffix.upper().lstrip(".")
        meta: dict[str, Any] = {
            "Format": ext or "Image",
            "File size": f"{node.size:,} B",
        }
        try:
            from crush.parsers.exif_reader import extract_exif, format_for_metadata
            exif_raw = extract_exif(raw)
            if exif_raw:
                meta.update(format_for_metadata(exif_raw))
        except Exception:
            pass
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
    # HEIC / HEIF / AVIF: ISO Base Media File Format — ftyp box at offset 4
    if len(peek) >= 12 and peek[4:8] == b"ftyp" and peek[8:12] in _ISOBMFF_IMAGE_BRANDS:
        return True
    # JPEG XL: bare codestream
    if peek[:2] == b"\xFF\x0A":
        return True
    # JPEG XL: ISOBMFF container
    if len(peek) >= 12 and peek[:12] == _JXL_CONTAINER_SIG:
        return True
    return False
