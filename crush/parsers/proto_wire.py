# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Shared Protobuf wire-format primitives.

Only low-level parsing utilities live here — no field interpretation, no schema
logic. Higher-level decoders (protobuf_parser, segb_parser) import from here
and apply their own semantics on top.
"""
from __future__ import annotations


def read_varint(data: bytes, idx: int) -> tuple[int | None, int]:
    """Read a varint from *data* starting at *idx*.

    Returns ``(value, new_idx)`` on success or ``(None, idx)`` on truncation /
    overflow. Accepts at most 10 bytes per the Protobuf spec (64-bit values).
    """
    result = 0
    shift = 0
    while idx < len(data) and shift < 64:
        b = data[idx]
        idx += 1
        result |= (b & 0x7F) << shift
        if b < 0x80:
            return result, idx
        shift += 7
    return None, idx
