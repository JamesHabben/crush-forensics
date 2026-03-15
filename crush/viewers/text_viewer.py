# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Text viewer — plain text and JSON."""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget


class TextView(QWidget):
    """Viewer for plain text and JSON content."""

    def __init__(self, data: str | bytes, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

        if isinstance(data, bytes):
            text = data.decode("utf-8", errors="replace")
        else:
            text = str(data)

        # Pretty-print JSON if possible
        if text.lstrip().startswith(("{", "[")):
            try:
                import json
                text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
            except Exception:
                pass

        self._editor.setPlainText(text)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._editor = QPlainTextEdit()
        self._editor.setReadOnly(True)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        font = QFont("Courier New", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._editor.setFont(font)

        layout.addWidget(self._editor)
