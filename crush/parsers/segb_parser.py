# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""SEGB v1/v2 parser (vendored from ccl-segb, MIT)."""
from __future__ import annotations

from io import BytesIO
from typing import Any

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import AbstractParser, ParseResult
from crush.third_party.ccl_segb import ccl_segb1, ccl_segb2
from crush.third_party.ccl_segb.ccl_segb_common import bytes_to_hexview


class SegbParser(AbstractParser):
    SUPPORTED_EXTENSIONS = [".segb", ".segb1", ".segb2", ".biome"]
    DISPLAY_NAME = "SEGB (v1/v2)"

    # SEGB v1 header is 56 bytes; magic is at the last 4 bytes (offset 52 = 0x34)
    _SEGB_V1_MAGIC_OFFSET = 52

    def can_parse(self, path: str, peek_bytes: bytes) -> bool:
        if any(path.lower().endswith(ext) for ext in self.SUPPORTED_EXTENSIONS):
            return True
        # SEGB v2: magic at offset 0
        if peek_bytes.startswith(b"SEGB"):
            return True
        # SEGB v1: magic at offset 52 (0x34), end of the 56-byte file header
        end = self._SEGB_V1_MAGIC_OFFSET + 4
        if len(peek_bytes) >= end and peek_bytes[self._SEGB_V1_MAGIC_OFFSET:end] == b"SEGB":
            return True
        return False

    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        import logging
        _logger = logging.getLogger(__name__)
        try:
            raw = vfs.read(node)
            stream = BytesIO(raw)

            is_v2 = ccl_segb2.stream_matches_segbv2_signature(stream)
            stream.seek(0)
            is_v1 = ccl_segb1.stream_matches_segbv1_signature(stream) if not is_v2 else False
            stream.seek(0)

            if is_v2:
                rows, parse_error = _read_v2(stream)
                version = "v2"
            elif is_v1:
                rows, parse_error = _read_v1(stream)
                version = "v1"
            else:
                return ParseResult(
                    viewer_type="hex",
                    data=raw,
                    metadata={
                        "Parse error": "Not a recognized SEGB v1/v2 file",
                        "Format": "SEGB (unrecognized)",
                        "File size": f"{node.size:,} B",
                    },
                )

            data = {
                "SEGB": {
                    "columns": [
                        "Index", "Offset", "State",
                        "Timestamp1", "Timestamp2",
                        "CRC Passed", "Data Length", "Data (hex preview)",
                    ],
                    "rows": rows,
                }
            }
            meta: dict[str, Any] = {
                "Format": "SEGB",
                "Version": version,
                "File size": f"{node.size:,} B",
                "Records": f"{len(rows):,}",
            }
            if parse_error:
                meta["Parse warning"] = parse_error
            return ParseResult(viewer_type="table", data=data, metadata=meta)

        except Exception as exc:
            _logger.warning("SEGB parse error for %s: %s", node.path, exc)
            try:
                raw_bytes = vfs.read(node)
            except Exception:
                raw_bytes = b""
            return ParseResult(
                viewer_type="hex",
                data=raw_bytes,
                metadata={
                    "Parse error": str(exc),
                    "Format": "SEGB (parse failed)",
                    "File size": f"{node.size:,} B",
                },
            )


def _read_v1(stream: BytesIO) -> tuple[list[list[Any]], str]:
    rows: list[list[Any]] = []
    error = ""
    try:
        for idx, entry in enumerate(ccl_segb1.read_segb1_stream(stream)):
            try:
                preview = bytes_to_hexview(entry.data, max_bytes=64)
                rows.append([
                    idx,
                    entry.data_start_offset,
                    entry.state.name,
                    _fmt_ts(entry.timestamp1),
                    _fmt_ts(entry.timestamp2),
                    entry.crc_passed,
                    len(entry.data),
                    preview,
                ])
            except Exception as exc:
                error = f"Record {idx} failed: {exc}"
                break
    except Exception as exc:
        error = str(exc)
    return rows, error


def _read_v2(stream: BytesIO) -> tuple[list[list[Any]], str]:
    rows: list[list[Any]] = []
    error = ""
    try:
        for idx, entry in enumerate(ccl_segb2.read_segb2_stream(stream)):
            try:
                preview = bytes_to_hexview(entry.data, max_bytes=64)
                rows.append([
                    idx,
                    entry.data_start_offset,
                    entry.state.name,
                    _fmt_ts(entry.metadata.creation),
                    "",
                    entry.crc_passed,
                    len(entry.data),
                    preview,
                ])
            except Exception as exc:
                error = f"Record {idx} failed: {exc}"
                break
    except Exception as exc:
        error = str(exc)
    return rows, error


def _fmt_ts(ts: object) -> str:
    try:
        return str(ts)
    except Exception:
        return ""
