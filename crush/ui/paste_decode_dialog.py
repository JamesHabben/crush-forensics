# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Paste & Decode dialog — decode hex/base64/text and open in the appropriate viewer."""
from __future__ import annotations

import base64
import re

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# (display_label, filename_hint, parser_display_name)
#   filename_hint   — passed to BytesVFS so extension-based parsers activate
#   parser_display_name — None = auto-detect, "__hex__" = always open as raw hex
_FORMATS: list[tuple[str, str, str | None]] = [
    ("Auto-detect",                    "data.bin",      None),
    ("Binary plist (bplist)",          "data.bplist",   "Property list (plist)"),
    ("XML / Text plist",               "data.plist",    "Property list (plist)"),
    ("JSON",                           "data.json",     "JSON document"),
    ("XML",                            "data.xml",      "XML document"),
    ("SQLite database",                "data.db",       "SQLite database"),
    ("Realm database",                 "data.realm",    "Realm Database"),
    ("Android Binary XML (ABX)",       "data.abx",      "Android Binary XML (ABX)"),
    ("SEGB / Biome",                   "data.segb",     "SEGB (v1/v2)"),
    ("Protobuf (schema-less)",         "data.bin",      "Protobuf (schema-less)"),
    ("Hex view (raw bytes)",           "data.bin",      "__hex__"),
]

_INPUT_ENCODINGS = ["Auto", "Hex", "Base64", "UTF-8 text"]


def _try_decode_input(text: str, encoding: str) -> tuple[bytes | None, str]:
    """Decode *text* according to *encoding*.

    Returns (bytes_or_None, status_message).
    """
    text = text.strip()
    if not text:
        return None, "Paste data above"

    if encoding == "Hex" or encoding == "Auto":
        cleaned = re.sub(r"[\s:_-]", "", text)
        if re.fullmatch(r"[0-9a-fA-F]+", cleaned) and len(cleaned) % 2 == 0:
            try:
                data = bytes.fromhex(cleaned)
                return data, f"{len(data):,} bytes  (hex)"
            except ValueError:
                pass
        if encoding == "Hex":
            return None, "Invalid hex input"

    if encoding == "Base64" or encoding == "Auto":
        # Strip line breaks (MIME wrapping) but not spaces — spaces indicate plain text
        b64_candidate = re.sub(r"[\r\n]", "", text)
        if re.fullmatch(r"[A-Za-z0-9+/=]+", b64_candidate) and len(b64_candidate) >= 4:
            try:
                data = base64.b64decode(b64_candidate + "==")
                return data, f"{len(data):,} bytes  (base64)"
            except Exception:
                pass
        if encoding == "Base64":
            return None, "Invalid base64 input"

    # UTF-8 text fallback
    data = text.encode("utf-8", errors="replace")
    return data, f"{len(data):,} bytes  (UTF-8 text)"


class PasteDecodeDialog(QDialog):
    """Dialog that lets the user paste hex/base64/text and open it as a specific format.

    Emits ``open_requested(bytes, filename_hint, parser_display_name)`` when the user
    clicks Open.  The main window connects to this signal and opens the appropriate tab.
    """

    open_requested: Signal = Signal(bytes, str, object)  # (data, filename_hint, display_name|None)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Paste & Decode")
        self.setMinimumSize(560, 380)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self._update_status)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        root.addWidget(QLabel("Paste data (hex, base64, or plain text):"))

        self._paste_area = QPlainTextEdit()
        self._paste_area.setPlaceholderText(
            "62706c6973743030…   (hex)\n"
            "YnBsaXN0MDA…       (base64)\n"
            "<?xml version…     (text)"
        )
        self._paste_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._paste_area.textChanged.connect(self._debounce.start)
        root.addWidget(self._paste_area, stretch=1)

        options_row = QHBoxLayout()

        options_row.addWidget(QLabel("Input encoding:"))
        self._encoding_combo = QComboBox()
        self._encoding_combo.addItems(_INPUT_ENCODINGS)
        self._encoding_combo.currentTextChanged.connect(self._update_status)
        options_row.addWidget(self._encoding_combo)

        options_row.addSpacing(16)

        options_row.addWidget(QLabel("Open as:"))
        self._format_combo = QComboBox()
        for label, _, _ in _FORMATS:
            self._format_combo.addItem(label)
        options_row.addWidget(self._format_combo)

        options_row.addStretch()
        root.addLayout(options_row)

        self._status_label = QLabel("Paste data above")
        self._status_label.setStyleSheet("color: gray;")
        root.addWidget(self._status_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self._open_btn = QPushButton("Open")
        self._open_btn.setDefault(True)
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._on_open)
        buttons.addWidget(self._open_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        buttons.addWidget(close_btn)
        root.addLayout(buttons)

    def _update_status(self) -> None:
        text = self._paste_area.toPlainText()
        encoding = self._encoding_combo.currentText()
        data, msg = _try_decode_input(text, encoding)
        self._status_label.setText(msg)
        self._status_label.setStyleSheet("color: gray;" if data is None else "color: green;")
        self._open_btn.setEnabled(data is not None)

    def _on_open(self) -> None:
        text = self._paste_area.toPlainText()
        encoding = self._encoding_combo.currentText()
        data, _ = _try_decode_input(text, encoding)
        if data is None:
            return
        idx = self._format_combo.currentIndex()
        _, filename_hint, parser_display_name = _FORMATS[idx]
        self.open_requested.emit(data, filename_hint, parser_display_name)
