# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Tests for MMKVKeyDialog's key_bytes() hex/text handling."""
from __future__ import annotations

from crush.ui.mmkv_key_dialog import MMKVKeyDialog


def test_text_mode_encodes_utf8(qapp) -> None:
    dialog = MMKVKeyDialog()
    dialog._key_edit.setText("my passphrase")
    assert dialog.is_hex() is False
    assert dialog.key_bytes() == "my passphrase".encode("utf-8")


def test_text_mode_does_not_interpret_hex_looking_text_as_hex(qapp) -> None:
    """A passphrase that happens to look like hex must stay literal text unless
    the user explicitly ticks Hex — no shape-based guessing."""
    dialog = MMKVKeyDialog()
    dialog._key_edit.setText("1234abcd")
    assert dialog.key_bytes() == b"1234abcd"


def test_hex_mode_decodes_plain_hex(qapp) -> None:
    dialog = MMKVKeyDialog()
    dialog._key_edit.setText("deadbeef")
    dialog._hex_cb.setChecked(True)
    assert dialog.key_bytes() == bytes.fromhex("deadbeef")


def test_hex_mode_strips_0x_prefix_and_separators(qapp) -> None:
    dialog = MMKVKeyDialog()
    dialog._key_edit.setText("0xDE:AD BE-EF")
    dialog._hex_cb.setChecked(True)
    assert dialog.key_bytes() == bytes.fromhex("deadbeef")


def test_hex_mode_invalid_hex_returns_none(qapp) -> None:
    dialog = MMKVKeyDialog()
    dialog._key_edit.setText("not hex at all!")
    dialog._hex_cb.setChecked(True)
    assert dialog.key_bytes() is None


def test_empty_key_returns_none(qapp) -> None:
    dialog = MMKVKeyDialog()
    assert dialog.key_bytes() is None


def test_aes256_checkbox_defaults_off(qapp) -> None:
    dialog = MMKVKeyDialog()
    assert dialog.is_aes256() is False
    dialog._aes256_cb.setChecked(True)
    assert dialog.is_aes256() is True
