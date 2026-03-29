# SPDX-License-Identifier: Apache-2.0
"""Tests for FormatDatabase and encoding detection."""
from __future__ import annotations

from crush.core.format_db import FormatDatabase, FormatMatch

# ---------------------------------------------------------------------------
# FormatDatabase — singleton
# ---------------------------------------------------------------------------

def test_format_db_singleton() -> None:
    a = FormatDatabase.get()
    b = FormatDatabase.get()
    assert a is b


def test_format_db_all_formats_nonempty() -> None:
    formats = FormatDatabase.get().all_formats()
    assert len(formats) > 0
    assert all(isinstance(f, FormatMatch) for f in formats)


def test_format_db_all_formats_have_names() -> None:
    for fmt in FormatDatabase.get().all_formats():
        assert fmt.name, f"Format with empty name: {fmt}"


# ---------------------------------------------------------------------------
# FormatDatabase.identify() — magic bytes
# ---------------------------------------------------------------------------

_SQLITE_MAGIC = b"SQLite format 3\x00" + b"\x00" * 512

def test_identify_sqlite_by_magic() -> None:
    fmt = FormatDatabase.get().identify(_SQLITE_MAGIC, "unknown_file")
    assert fmt is not None
    assert "SQLite" in fmt.name


def test_identify_sqlite_has_parser_class() -> None:
    fmt = FormatDatabase.get().identify(_SQLITE_MAGIC, "unknown_file")
    assert fmt is not None
    assert fmt.parser_class == "SQLiteParser"


def test_identify_sqlite_has_platforms() -> None:
    fmt = FormatDatabase.get().identify(_SQLITE_MAGIC, "unknown_file")
    assert fmt is not None
    assert fmt.platforms  # non-empty


def test_identify_sqlite_links_is_list() -> None:
    fmt = FormatDatabase.get().identify(_SQLITE_MAGIC, "unknown_file")
    assert fmt is not None
    assert isinstance(fmt.links, list)


# ---------------------------------------------------------------------------
# FormatDatabase.identify() — no extension fallback
# ---------------------------------------------------------------------------

def test_identify_extension_only_returns_none() -> None:
    # Random bytes that won't match any magic pattern
    junk = b"\x00\x00\x00\x00" * 128
    fmt = FormatDatabase.get().identify(junk, "com.apple.test.plist")
    assert fmt is None


def test_identify_no_match_returns_none() -> None:
    junk = b"\x00\x00\x00\x00" * 128
    fmt = FormatDatabase.get().identify(junk, "totally_unknown.xyz999")
    assert fmt is None


def test_identify_empty_bytes_no_crash() -> None:
    result = FormatDatabase.get().identify(b"", "empty_file")
    # Either None or a valid match — must not raise
    assert result is None or isinstance(result, FormatMatch)


# ---------------------------------------------------------------------------
# FormatDatabase.by_parser_class()
# ---------------------------------------------------------------------------

def test_by_parser_class_sqlite() -> None:
    fmt = FormatDatabase.get().by_parser_class("SQLiteParser")
    assert fmt is not None
    assert fmt.parser_class == "SQLiteParser"


def test_by_parser_class_plist() -> None:
    fmt = FormatDatabase.get().by_parser_class("PlistParser")
    assert fmt is not None
    assert fmt.parser_class == "PlistParser"


def test_by_parser_class_unknown_returns_none() -> None:
    fmt = FormatDatabase.get().by_parser_class("NonExistentParser")
    assert fmt is None


# ---------------------------------------------------------------------------
# FormatMatch structure
# ---------------------------------------------------------------------------

def test_format_match_fields() -> None:
    fmt = FormatDatabase.get().by_parser_class("SQLiteParser")
    assert fmt is not None
    # Check all fields exist and have expected types
    assert isinstance(fmt.name, str)
    assert isinstance(fmt.short_name, str)
    assert isinstance(fmt.category, str)
    assert isinstance(fmt.forensic_relevance, str)
    assert isinstance(fmt.platforms, str)
    assert isinstance(fmt.links, list)
    for label, url in fmt.links:
        assert isinstance(label, str)
        assert isinstance(url, str)
