# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""ABX viewer — split pane showing the parsed tree and reconstructed XML.

The left pane reuses the standard TreeViewer for the nested dict structure.
The right pane shows the reconstructed human-readable XML for copy/reference.
The data dict passed in has the shape:

    {
        "tree":    { ... },   # nested dict for TreeViewer
        "xml_str": "..."      # reconstructed XML string
    }
"""
from __future__ import annotations

from PySide6.QtCore import Qt
import re

from PySide6.QtGui import QFont, QColor, QSyntaxHighlighter, QTextCharFormat, QTextOption
from PySide6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from crush.viewers.tree_viewer import TreeViewer


class AbxViewer(QWidget):
    """Split-pane viewer for Android Binary XML (ABX) files."""

    def __init__(self, data: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui(data)

    def _build_ui(self, data: dict) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: tree view of parsed structure
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        left_header = QLabel("  Parsed structure")
        left_header.setFixedHeight(28)
        left_header.setStyleSheet(
            "background: palette(mid); color: palette(text); font-size: 11px;"
        )
        left_layout.addWidget(left_header)

        tree_widget = TreeViewer(data.get("tree", {}), self)
        left_layout.addWidget(tree_widget)
        splitter.addWidget(left)

        # Right: reconstructed XML
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        right_header = QLabel("  Reconstructed XML")
        right_header.setFixedHeight(28)
        right_header.setStyleSheet(
            "background: palette(mid); color: palette(text); font-size: 11px;"
        )
        right_layout.addWidget(right_header)

        xml_editor = QPlainTextEdit()
        xml_editor.setReadOnly(True)
        # Visual wrap to avoid horizontal scrolling; no actual line breaks inserted.
        xml_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        xml_editor.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        xml_editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        font = QFont("Courier New", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        xml_editor.setFont(font)
        _XmlHighlighter(xml_editor.document())
        xml_editor.setPlainText(data.get("xml_str", ""))
        right_layout.addWidget(xml_editor)

        splitter.addWidget(right)
        splitter.setSizes([400, 400])

        layout.addWidget(splitter)


class _XmlHighlighter(QSyntaxHighlighter):
    def __init__(self, document: object) -> None:
        super().__init__(document)  # type: ignore[arg-type]
        self._fmt_tag = QTextCharFormat()
        self._fmt_tag.setForeground(QColor("#005a9c"))
        self._fmt_attr = QTextCharFormat()
        self._fmt_attr.setForeground(QColor("#7a3e9d"))
        self._fmt_attr_value = QTextCharFormat()
        self._fmt_attr_value.setForeground(QColor("#2a7b2e"))
        self._tag_re = re.compile(r"</?\s*[^>\s/]+")
        self._attr_re = re.compile(r"\s+([A-Za-z_:\-][\w:.-]*)\s*=")
        self._attr_value_re = re.compile(r"=\s*\"([^\"\\]|\\.)*\"")

    def highlightBlock(self, text: str) -> None:  # type: ignore[override]
        for m in self._tag_re.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._fmt_tag)
        for m in self._attr_re.finditer(text):
            self.setFormat(m.start(1), m.end(1) - m.start(1), self._fmt_attr)
        for m in self._attr_value_re.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._fmt_attr_value)
