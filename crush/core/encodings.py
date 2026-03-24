# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Encoding detection for raw byte buffers."""
from __future__ import annotations


def detect_encoding(raw: bytes) -> tuple[str, str]:
    """Return (decoded_text, encoding_label). Handles BOM and common iOS encodings."""
    # Explicit BOM — most reliable
    if raw[:3] == b"\xef\xbb\xbf":
        return raw[3:].decode("utf-8", errors="replace"), "UTF-8 BOM"
    if raw[:2] == b"\xff\xfe":
        return raw[2:].decode("utf-16-le", errors="replace"), "UTF-16 LE"
    if raw[:2] == b"\xfe\xff":
        return raw[2:].decode("utf-16-be", errors="replace"), "UTF-16 BE"
    # Strict UTF-8
    try:
        return raw.decode("utf-8"), "UTF-8"
    except UnicodeDecodeError:
        pass
    # Heuristic: UTF-16 LE without BOM — ASCII chars have null byte in odd positions
    if len(raw) >= 8:
        sample = raw[: min(len(raw), 256)]
        odd_nulls = sum(1 for i in range(1, len(sample), 2) if sample[i] == 0)
        if odd_nulls > len(sample) // 4:
            try:
                return raw.decode("utf-16-le", errors="replace"), "UTF-16 LE (no BOM)"
            except Exception:
                pass
    return raw.decode("utf-8", errors="replace"), "UTF-8 (lossy)"
