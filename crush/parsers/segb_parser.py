# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""SEGB v1/v2 parser (vendored from ccl-segb, MIT)."""
from __future__ import annotations

import logging
import struct
from io import BytesIO
from typing import Any

_logger = logging.getLogger(__name__)

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import AbstractParser, ParseResult
from crush.third_party.ccl_segb import ccl_segb1, ccl_segb2
from crush.third_party.ccl_segb.ccl_segb_common import decode_cocoa_time

_COLUMNS_V1 = [
    "Index", "Offset", "State",
    "Timestamp1", "Timestamp2",
    "CRC Stored", "CRC Calc", "CRC Passed",
    "Payload Size",
    "Bundle ID", "Stream ID", "Payload Timestamp",
    "Payload",
]

_COLUMNS_V2 = [
    "Index", "Offset", "State",
    "Creation",
    "Trailer Offset", "Entry End Offset",
    "CRC Stored", "CRC Calc", "CRC Passed",
    "Payload Size",
    "Bundle ID", "Stream ID", "Payload Timestamp",
    "Payload",
]


class SegbParser(AbstractParser):
    SUPPORTED_EXTENSIONS = [".segb", ".segb1", ".segb2", ".biome"]
    DISPLAY_NAME = "SEGB (v1/v2)"

    _SEGB_V1_MAGIC_OFFSET = 52

    def can_parse(self, path: str, peek_bytes: bytes) -> bool:
        if any(path.lower().endswith(ext) for ext in self.SUPPORTED_EXTENSIONS):
            return True
        if peek_bytes.startswith(b"SEGB"):
            return True
        end = self._SEGB_V1_MAGIC_OFFSET + 4
        if len(peek_bytes) >= end and peek_bytes[self._SEGB_V1_MAGIC_OFFSET:end] == b"SEGB":
            return True
        return False

    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        try:
            raw = vfs.read(node)
            result = _detect_and_read(BytesIO(raw))
            if result is None:
                return ParseResult(
                    viewer_type="hex",
                    data=raw,
                    metadata={
                        "Parse error": "Not a recognized SEGB v1/v2 file",
                        "Format": "SEGB (unrecognized)",
                        "File size": f"{node.size:,} B",
                    },
                )
            version, columns, rows, parse_error = result
            meta: dict[str, Any] = {
                "Format": "SEGB",
                "Version": version,
                "File size": f"{node.size:,} B",
                "Records": f"{len(rows):,}",
            }
            if parse_error:
                meta["Parse warning"] = parse_error
            return ParseResult(
                viewer_type="table",
                data={"SEGB": {"columns": columns, "rows": rows}},
                metadata=meta,
            )
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


def _detect_and_read(
    stream: BytesIO,
) -> tuple[str, list[str], list[list[Any]], str] | None:
    """Detect SEGB version and parse; returns (version, columns, rows, error) or None."""
    if ccl_segb2.stream_matches_segbv2_signature(stream):
        stream.seek(0)
        columns, rows, error = _read_v2(stream)
        return "v2", columns, rows, error
    stream.seek(0)
    if ccl_segb1.stream_matches_segbv1_signature(stream):
        stream.seek(0)
        columns, rows, error = _read_v1(stream)
        return "v1", columns, rows, error
    return None


def _read_v1(stream: BytesIO) -> tuple[list[str], list[list[Any]], str]:
    rows: list[list[Any]] = []
    error = ""
    try:
        for idx, entry in enumerate(ccl_segb1.read_segb1_stream(stream)):
            try:
                bundle_id, stream_id, payload_ts = _extract_proto_fields(entry.data)
                rows.append([
                    idx,
                    entry.data_start_offset,
                    entry.state.name,
                    _fmt_ts(entry.timestamp1),
                    _fmt_ts(entry.timestamp2),
                    entry.metadata_crc,
                    entry.actual_crc,
                    entry.crc_passed,
                    len(entry.data),
                    bundle_id,
                    stream_id,
                    payload_ts,
                    _render_proto_payload(entry.data) or entry.data,
                ])
            except Exception as exc:
                error = f"Record {idx} failed: {exc}"
                break
    except Exception as exc:
        error = str(exc)
    return _COLUMNS_V1, rows, error


def _read_v2(stream: BytesIO) -> tuple[list[str], list[list[Any]], str]:
    rows: list[list[Any]] = []
    error = ""
    try:
        for idx, entry in enumerate(ccl_segb2.read_segb2_stream(stream)):
            try:
                bundle_id, stream_id, payload_ts = _extract_proto_fields(entry.data)
                rows.append([
                    idx,
                    entry.data_start_offset,
                    entry.state.name,
                    _fmt_ts(entry.metadata.creation),
                    entry.metadata.metadata_offset,
                    entry.metadata.end_offset,
                    entry.metadata_crc,
                    entry.actual_crc,
                    entry.crc_passed,
                    len(entry.data),
                    bundle_id,
                    stream_id,
                    payload_ts,
                    _render_proto_payload(entry.data) or entry.data,
                ])
            except Exception as exc:
                error = f"Record {idx} failed: {exc}"
                break
    except Exception as exc:
        error = str(exc)
    return _COLUMNS_V2, rows, error


def _fmt_ts(ts: object) -> str:
    try:
        return str(ts)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Minimal protobuf wire-format decoder (no external dependency)
# ---------------------------------------------------------------------------

def _read_varint(data: bytes, pos: int) -> tuple[int | None, int]:
    result = 0
    shift = 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, pos
        shift += 7
        if shift >= 64:
            return None, pos
    return None, pos


def _parse_protobuf(data: bytes) -> dict[int, Any]:
    """Parse protobuf wire format into {field_number: value}. Best-effort, stops on error."""
    result: dict[int, Any] = {}
    pos = 0
    while pos < len(data):
        tag, pos = _read_varint(data, pos)
        if tag is None:
            break
        field_num = tag >> 3
        wire_type = tag & 0x7
        if field_num == 0 or field_num > 200:
            break
        if wire_type == 0:  # varint
            val, pos = _read_varint(data, pos)
            if val is None:
                break
            result[field_num] = val
        elif wire_type == 1:  # 64-bit (double)
            if pos + 8 > len(data):
                break
            result[field_num] = struct.unpack_from("<d", data, pos)[0]
            pos += 8
        elif wire_type == 2:  # length-delimited
            length, pos = _read_varint(data, pos)
            if length is None or pos + length > len(data):
                break
            chunk = data[pos:pos + length]
            try:
                result[field_num] = chunk.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                result[field_num] = chunk
            pos += length
        elif wire_type == 5:  # 32-bit (float)
            if pos + 4 > len(data):
                break
            result[field_num] = struct.unpack_from("<f", data, pos)[0]
            pos += 4
        else:
            break
    return result


def _extract_proto_fields(payload: bytes) -> tuple[str, str, str]:
    """Return (bundle_id, stream_id, payload_timestamp_str) from a protobuf payload."""
    try:
        fields = _parse_protobuf(payload)
    except Exception:
        return "", "", ""

    bundle_id = fields.get(2, "")
    if not isinstance(bundle_id, str):
        bundle_id = ""

    stream_id = fields.get(3, "")
    if not isinstance(stream_id, str):
        stream_id = ""

    ts_val = fields.get(1)
    if isinstance(ts_val, float) and -1e10 < ts_val < 1e10:
        try:
            payload_ts = _fmt_ts(decode_cocoa_time(ts_val))
        except Exception:
            payload_ts = ""
    else:
        payload_ts = ""

    return bundle_id, stream_id, payload_ts


def _render_proto_payload(data: bytes) -> str:
    """Return a compact single-line protobuf representation, or '' if decoding fails."""
    try:
        fields = _parse_protobuf(data)
        if not fields:
            return ""
        parts = []
        for field_num, val in sorted(fields.items()):
            if isinstance(val, str):
                parts.append(f'{field_num}: "{val}"')
            elif isinstance(val, float):
                parts.append(f"{field_num}: {val:.6g}")
            elif isinstance(val, bytes):
                parts.append(f"{field_num}: <{len(val)}B>")
            else:
                parts.append(f"{field_num}: {val}")
        return "  |  ".join(parts)
    except Exception:
        return ""
