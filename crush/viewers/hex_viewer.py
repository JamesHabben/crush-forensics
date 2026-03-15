# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Hex viewer — displays raw bytes as hex + ASCII, 16 bytes per row."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QFont, QTextCursor


_BYTES_PER_ROW = 16
_MAX_BYTES = 1024 * 256  # Render at most 256 KB to keep the UI responsive


class HexViewer(QWidget):
    """Simple hex + ASCII dump viewer."""

    def __init__(self, data: bytes, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data = data
        self._view_data = data[:_MAX_BYTES]
        self._build_ui()
        self._load(self._view_data)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(6, 6, 6, 0)
        toolbar.setSpacing(8)

        self._search_mode = QComboBox()
        self._search_mode.addItems(["ASCII", "Hex"])
        toolbar.addWidget(self._search_mode)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search…")
        self._search_input.returnPressed.connect(self._search)
        toolbar.addWidget(self._search_input, stretch=1)

        self._search_btn = QPushButton("Find")
        self._search_btn.clicked.connect(self._search)
        toolbar.addWidget(self._search_btn)

        self._status = QLabel("")
        toolbar.addWidget(self._status)

        toolbar.addStretch(1)

        self._copy_hex_btn = QPushButton("Copy Hex")
        self._copy_hex_btn.clicked.connect(self._copy_hex)
        toolbar.addWidget(self._copy_hex_btn)

        self._copy_ascii_btn = QPushButton("Copy ASCII")
        self._copy_ascii_btn.clicked.connect(self._copy_ascii)
        toolbar.addWidget(self._copy_ascii_btn)

        self._copy_all_btn = QPushButton("Copy All")
        self._copy_all_btn.clicked.connect(self._copy_all)
        toolbar.addWidget(self._copy_all_btn)

        layout.addLayout(toolbar)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        font = QFont("Courier New", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._text.setFont(font)

        layout.addWidget(self._text)

    def _load(self, data: bytes) -> None:
        lines: list[str] = []

        for offset in range(0, len(data), _BYTES_PER_ROW):
            chunk = data[offset : offset + _BYTES_PER_ROW]

            # Offset column
            off_str = f"{offset:08X}"

            # Hex columns (two groups of 8, space-separated in the middle)
            hex_parts = [f"{b:02X}" for b in chunk]
            hex_left  = " ".join(hex_parts[:8])
            hex_right = " ".join(hex_parts[8:])
            hex_str   = f"{hex_left:<23}  {hex_right:<23}"

            # ASCII column
            ascii_str = "".join(
                chr(b) if 0x20 <= b < 0x7F else "." for b in chunk
            )

            lines.append(f"{off_str}  {hex_str}  {ascii_str}")

        if len(self._data) > _MAX_BYTES:
            lines.append(
                f"\n... truncated — showing first {_MAX_BYTES:,} of {len(self._data):,} bytes"
            )
        self._status.setText(
            f"{min(len(self._data), _MAX_BYTES):,} / {len(self._data):,} bytes"
        )

        self._text.setPlainText("\n".join(lines))

    def _search(self) -> None:
        query = self._search_input.text().strip()
        if not query:
            self._status.setText("Enter a search term")
            return

        mode = self._search_mode.currentText()
        if mode == "Hex":
            pattern = _parse_hex_query(query)
            if pattern is None:
                self._status.setText("Invalid hex pattern")
                return
            idx = self._view_data.find(pattern)
        else:
            hay = self._view_data.decode("latin-1")
            idx = hay.find(query)

        if idx < 0:
            self._status.setText("Not found")
            return

        self._scroll_to_offset(idx)
        self._status.setText(f"Found at 0x{idx:08X}")

    def _scroll_to_offset(self, offset: int) -> None:
        line = offset // _BYTES_PER_ROW
        block = self._text.document().findBlockByNumber(line)
        if not block.isValid():
            return
        cursor = self._text.textCursor()
        cursor.setPosition(block.position())
        self._text.setTextCursor(cursor)
        self._text.centerCursor()

    def _copy_hex(self) -> None:
        text = " ".join(f"{b:02X}" for b in self._view_data)
        QApplication.clipboard().setText(text)

    def _copy_ascii(self) -> None:
        text = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in self._view_data)
        QApplication.clipboard().setText(text)

    def _copy_all(self) -> None:
        QApplication.clipboard().setText(self._text.toPlainText())


def _parse_hex_query(query: str) -> bytes | None:
    cleaned = "".join(ch for ch in query if ch not in {" ", "\t", "\n", ":"})
    if len(cleaned) % 2 != 0:
        return None
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        return None
