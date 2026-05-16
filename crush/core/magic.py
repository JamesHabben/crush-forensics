# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Magic-byte helpers for fast file type detection."""
from __future__ import annotations

from typing import Final

try:
    import filetype  # type: ignore
except Exception:
    filetype = None

SQLITE_MAGIC: Final = b"SQLite format 3\x00"
BPLIST_MAGIC: Final = b"bplist"
XML_PLIST_SIG: Final = b"<?xml"
ABX_MAGIC: Final = b"ABX\x00"
SEGB_MAGIC: Final = b"SEGB"
# SEGB v1 header is 56 bytes; magic sits at the last 4 bytes (offset 52 = 0x34)
_SEGB_V1_MAGIC_OFFSET: Final = 52
# Realm: 24-byte file header, mnemonic "T-DB" at offset 16
REALM_MNEMONIC: Final = b"T-DB"
_REALM_MNEMONIC_OFFSET: Final = 16


def detect_fast_label(peek_bytes: bytes, path: str) -> str:
    """Return a fast type label using lightweight magic checks.

    Returns empty string when no fast label applies.
    """
    if filetype is not None:
        kind = filetype.guess(peek_bytes)
        if kind is not None:
            mime = getattr(kind, "mime", "")
            if isinstance(mime, str):
                if mime.startswith("image/"):
                    return "Image"
                if mime.startswith("audio/") or mime.startswith("video/"):
                    return "Media"
            ext = getattr(kind, "extension", "")
            if isinstance(ext, str) and ext:
                return ext.upper()

    if peek_bytes[_REALM_MNEMONIC_OFFSET : _REALM_MNEMONIC_OFFSET + 4] == REALM_MNEMONIC:
        return "Realm"
    if peek_bytes.startswith(SQLITE_MAGIC):
        return "SQLite"
    if peek_bytes.startswith(BPLIST_MAGIC):
        return "bplist"
    if peek_bytes.startswith(ABX_MAGIC):
        return "ABX"
    if peek_bytes.startswith(SEGB_MAGIC):
        return "SEGB"
    end = _SEGB_V1_MAGIC_OFFSET + len(SEGB_MAGIC)
    if len(peek_bytes) >= end and peek_bytes[_SEGB_V1_MAGIC_OFFSET:end] == SEGB_MAGIC:
        return "SEGB"
    if _looks_like_plist_xml(peek_bytes):
        return "plist"
    return ""


def _looks_like_plist_xml(peek_bytes: bytes) -> bool:
    if not peek_bytes.lstrip().startswith(XML_PLIST_SIG):
        return False
    text = peek_bytes[:2048].decode("utf-8", errors="ignore")
    return "<plist" in text.lower()
