# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Tests for the Value Inspector interpretation engine (_interpret)."""
from __future__ import annotations

import struct

import pytest

from crush.viewers.value_inspector import _interpret, _Row


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(rows: list[_Row], group: str, label: str) -> str | None | type[KeyError]:
    for r in rows:
        if r.group == group and r.label == label:
            return r.value
    return KeyError  # sentinel: row not present at all


def _present(rows: list[_Row], group: str, label: str) -> bool:
    return _get(rows, group, label) is not KeyError


def _value(rows: list[_Row], group: str, label: str) -> str:
    """Return the value; raises AssertionError if the row is absent or None."""
    v = _get(rows, group, label)
    assert v is not KeyError and v is not None, f"[{group}] {label!r} has no value"
    assert isinstance(v, str)
    return v


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_empty_string_returns_empty_list(self) -> None:
        assert _interpret("") == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        assert _interpret("   \t\n") == []


# ---------------------------------------------------------------------------
# Integer group — decimal input
# ---------------------------------------------------------------------------

class TestIntegerDecimal:
    def test_decimal_shows_decimal_and_hex(self) -> None:
        rows = _interpret("255")
        assert _value(rows, "Integer", "Decimal") == "255"
        assert _value(rows, "Integer", "Hex") == "0xff"

    def test_signed_32bit_positive(self) -> None:
        rows = _interpret("2147483647")  # INT32_MAX
        assert _value(rows, "Integer", "Signed 32-bit") == "2147483647"

    def test_signed_32bit_wraps_for_large_uint32(self) -> None:
        rows = _interpret("3000000000")
        signed = _value(rows, "Integer", "Signed 32-bit")
        assert int(signed) < 0  # wraps to negative

    def test_large_decimal_no_le_variants(self) -> None:
        """LE variants only appear for hex-byte input, not plain decimal."""
        rows = _interpret("1718000000")
        assert not _present(rows, "Integer", "Decimal (LE)")

    def test_0x_prefix_parsed_as_integer(self) -> None:
        rows = _interpret("0xff")
        assert _value(rows, "Integer", "Decimal") == "255"
        assert _value(rows, "Integer", "Hex") == "0xff"


# ---------------------------------------------------------------------------
# Integer group — hex-byte input (BE and LE)
# ---------------------------------------------------------------------------

class TestIntegerHexBytes:
    def test_4_bytes_be_and_le(self) -> None:
        # c0 a8 01 01 → BE = 0xc0a80101, LE = 0x0101a8c0
        rows = _interpret("c0 a8 01 01")
        assert _value(rows, "Integer", "Decimal") == "3,232,235,777"
        assert _value(rows, "Integer", "Decimal (LE)") == "16,885,952"

    def test_6_bytes_le_present(self) -> None:
        rows = _interpret("f7 f8 f9 fa fb fc")
        be = int(_value(rows, "Integer", "Decimal").replace(",", ""))
        le = int(_value(rows, "Integer", "Decimal (LE)").replace(",", ""))
        assert be != le

    def test_odd_nibble_truncated_silently(self) -> None:
        # "f7 f8 f" truncates to "f7 f8" (2 bytes)
        rows_full = _interpret("f7 f8")
        rows_trunc = _interpret("f7 f8 f")
        assert _value(rows_full, "Integer", "Decimal") == _value(rows_trunc, "Integer", "Decimal")

    def test_hex_bytes_signed_32bit_negative(self) -> None:
        rows = _interpret("c0 a8 01 01")
        signed = _value(rows, "Integer", "Signed 32-bit")
        assert int(signed) < 0


# ---------------------------------------------------------------------------
# Float group
# ---------------------------------------------------------------------------

class TestFloat:
    def test_float_string_shows_double(self) -> None:
        rows = _interpret("3.14159")
        assert _value(rows, "Float", "Double (64-bit)").startswith("3.")

    def test_float_does_not_trigger_cocoa_for_small_value(self) -> None:
        # 3.14159 < 1_000_000 → Cocoa guard must suppress it
        rows = _interpret("3.14159")
        assert _get(rows, "Timestamp", "Cocoa / Apple (s)") is None

    def test_4_byte_hex_shows_float32_be_and_le(self) -> None:
        # Known BE float: 0x3fc00000 = 1.5 in IEEE-754
        be_bytes = struct.pack(">f", 1.5)
        hex_input = " ".join(f"{b:02x}" for b in be_bytes)
        rows = _interpret(hex_input)
        assert float(_value(rows, "Float", "Float32 · 4 bytes BE")) == pytest.approx(1.5)
        # LE interpretation of same bytes is a different (non-trivial) value
        assert _present(rows, "Float", "Float32 · 4 bytes LE")

    def test_8_byte_hex_shows_double_be_and_le(self) -> None:
        be_bytes = struct.pack(">d", 1.5)
        hex_input = " ".join(f"{b:02x}" for b in be_bytes)
        rows = _interpret(hex_input)
        assert float(_value(rows, "Float", "Double · 8 bytes BE")) == pytest.approx(1.5)
        assert _present(rows, "Float", "Double · 8 bytes LE")


# ---------------------------------------------------------------------------
# Timestamp group
# ---------------------------------------------------------------------------

class TestTimestamp:
    def test_unix_second_in_range(self) -> None:
        rows = _interpret("1718000000")
        ts = _value(rows, "Timestamp", "Unix (s)")
        assert "2024" in ts

    def test_unix_ms_in_range(self) -> None:
        rows = _interpret("1718000000000")
        ts = _value(rows, "Timestamp", "Unix (ms)")
        assert "2024" in ts

    def test_cocoa_second_in_range(self) -> None:
        # 760_000_000 Cocoa seconds ≈ 2025-02-03
        rows = _interpret("760000000")
        ts = _value(rows, "Timestamp", "Cocoa / Apple (s)")
        assert "2025" in ts

    def test_small_float_not_cocoa(self) -> None:
        rows = _interpret("12345.6789")
        assert _get(rows, "Timestamp", "Cocoa / Apple (s)") is None

    def test_out_of_range_int_no_unix(self) -> None:
        rows = _interpret("1")  # 1970-01-01 → below _TS_S_MIN
        assert _get(rows, "Timestamp", "Unix (s)") is None


# ---------------------------------------------------------------------------
# UUID group
# ---------------------------------------------------------------------------

class TestUUID:
    UUID_DASHED = "550e8400-e29b-41d4-a716-446655440000"
    UUID_HEX    = "550e8400e29b41d4a716446655440000"

    def test_dashed_uuid_parsed(self) -> None:
        rows = _interpret(self.UUID_DASHED)
        assert _value(rows, "UUID", "UUID") == self.UUID_DASHED

    def test_hex_uuid_parsed(self) -> None:
        rows = _interpret(self.UUID_HEX)
        assert _value(rows, "UUID", "UUID") == self.UUID_DASHED

    def test_non_uuid_string_shows_none(self) -> None:
        rows = _interpret("hello world")
        assert _get(rows, "UUID", "UUID") is None


# ---------------------------------------------------------------------------
# Network group
# ---------------------------------------------------------------------------

class TestNetwork:
    def test_4_byte_hex_ipv4_be(self) -> None:
        rows = _interpret("c0 a8 01 01")
        assert _value(rows, "Network", "IPv4 (big-endian)") == "192.168.1.1"

    def test_4_byte_hex_ipv4_le(self) -> None:
        rows = _interpret("c0 a8 01 01")
        assert _value(rows, "Network", "IPv4 (little-endian)") == "1.1.168.192"

    def test_6_byte_hex_mac(self) -> None:
        rows = _interpret("f7 f8 f9 fa fb fc")
        assert _value(rows, "Network", "MAC address") == "f7:f8:f9:fa:fb:fc"

    def test_colon_mac_input(self) -> None:
        rows = _interpret("aa:bb:cc:dd:ee:ff")
        assert _value(rows, "Network", "MAC address") == "aa:bb:cc:dd:ee:ff"

    def test_5_byte_hex_no_ipv4(self) -> None:
        # 5 bytes → too long for IPv4, no IPv4 row should be filled
        rows = _interpret("c0 a8 01 01 ff")
        assert _get(rows, "Network", "IPv4 (big-endian)") is None


# ---------------------------------------------------------------------------
# Text group
# ---------------------------------------------------------------------------

class TestText:
    def test_ascii_hello(self) -> None:
        rows = _interpret("48 65 6c 6c 6f")
        assert _value(rows, "Text", "ASCII (hex bytes)") == "Hello"
        assert _value(rows, "Text", "UTF-8 (hex bytes)") == "Hello"

    def test_non_printable_shown_as_dots(self) -> None:
        rows = _interpret("f7 f8 f9")
        ascii_val = _value(rows, "Text", "ASCII (hex bytes)")
        assert ascii_val == "..."

    def test_valid_utf8_non_ascii(self) -> None:
        # é = U+00E9, UTF-8: c3 a9
        rows = _interpret("c3 a9")
        assert _value(rows, "Text", "UTF-8 (hex bytes)") == "é"

    def test_invalid_utf8_shows_none(self) -> None:
        # 0xf7 alone is not valid UTF-8
        rows = _interpret("f7")
        assert _get(rows, "Text", "UTF-8 (hex bytes)") is None

    def test_no_text_group_for_plain_decimal(self) -> None:
        rows = _interpret("1718000000")
        assert not _present(rows, "Text", "ASCII (hex bytes)")
