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

    if peek_bytes.startswith(SQLITE_MAGIC):
        return "SQLite"
    if peek_bytes.startswith(BPLIST_MAGIC):
        return "bplist"
    if peek_bytes.startswith(ABX_MAGIC):
        return "ABX"
    if peek_bytes.startswith(SEGB_MAGIC):
        return "SEGB"
    if _looks_like_plist_xml(peek_bytes, path):
        return "plist"
    return ""


def _looks_like_plist_xml(peek_bytes: bytes, path: str) -> bool:
    if not peek_bytes.lstrip().startswith(XML_PLIST_SIG):
        return False
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
