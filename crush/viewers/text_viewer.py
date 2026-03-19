# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Text viewer — plain text and JSON with line numbers."""
from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QFont, QPainter, QPalette
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget


class _LineNumberArea(QWidget):
    def __init__(self, editor: "_CodeEditor") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:  # type: ignore[override]
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event: object) -> None:  # type: ignore[override]
        self._editor.line_number_area_paint(event)


class _CodeEditor(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self._line_number_area = _LineNumberArea(self)
        self._line_number_area.setVisible(True)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self._update_line_number_area_width(0)
        self.refresh_line_numbers()

    def line_number_area_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return 8 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_number_area_width(self, _: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)
        self._line_number_area.update()

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def refresh_line_numbers(self) -> None:
        self._update_line_number_area_width(0)
        self._line_number_area.update()
        self.viewport().update()

    def setPlainText(self, text: str) -> None:  # type: ignore[override]
        super().setPlainText(text)
        self.refresh_line_numbers()

    def resizeEvent(self, event: object) -> None:  # type: ignore[override]
        super().resizeEvent(event)  # type: ignore[arg-type]
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint(self, event: object) -> None:
        painter = QPainter(self._line_number_area)
        bg = self.palette().color(QPalette.ColorRole.AlternateBase)
        painter.fillRect(event.rect(), bg)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(self.palette().color(QPalette.ColorRole.Text))
                painter.drawText(
                    0,
                    top,
                    self._line_number_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number,
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def _highlight_current_line(self) -> None:
        return


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
        self._editor.refresh_line_numbers()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._editor = _CodeEditor()
        self._editor.setReadOnly(True)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        font = QFont("Courier New", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._editor.setFont(font)

        layout.addWidget(self._editor)
