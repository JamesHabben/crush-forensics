# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Paste & Decode dialog — decode hex/base64/text and show the result inline."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from crush.core.paste_decode import FORMATS as _FORMATS
from crush.core.paste_decode import try_decode_input as _try_decode_input

_INPUT_ENCODINGS = ["Auto", "Hex", "Base64", "UTF-8 text"]


class PasteDecodeDialog(QDialog):
    """Dialog that lets the user paste hex/base64/text and view the decoded result inline."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Paste & Decode")
        self.setMinimumSize(600, 300)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self._update_status)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        self._splitter = QSplitter(Qt.Orientation.Vertical)

        # --- top pane: paste input + controls ---
        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setSpacing(8)
        top_layout.setContentsMargins(12, 12, 12, 8)

        top_layout.addWidget(QLabel("Paste data (hex, base64, or plain text):"))

        self._paste_area = QPlainTextEdit()
        self._paste_area.setPlaceholderText(
            "62706c6973743030…   (hex)\n"
            "YnBsaXN0MDA…       (base64)\n"
            "<?xml version…     (text)"
        )
        self._paste_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._paste_area.textChanged.connect(self._debounce.start)
        top_layout.addWidget(self._paste_area, stretch=1)

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
        top_layout.addLayout(options_row)

        self._status_label = QLabel("Paste data above")
        self._status_label.setStyleSheet("color: gray;")
        top_layout.addWidget(self._status_label)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch()
        self._open_btn = QPushButton("Open")
        self._open_btn.setDefault(True)
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._on_open)
        buttons_row.addWidget(self._open_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        buttons_row.addWidget(close_btn)
        top_layout.addLayout(buttons_row)

        self._splitter.addWidget(top)

        # --- bottom pane: viewer (hidden until first decode) ---
        self._viewer_pane = QWidget()
        self._viewer_layout = QVBoxLayout(self._viewer_pane)
        self._viewer_layout.setContentsMargins(4, 0, 4, 4)
        self._viewer_layout.setSpacing(0)
        self._viewer_pane.hide()

        self._splitter.addWidget(self._viewer_pane)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        root.addWidget(self._splitter)

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

        # Remove previous viewer widget
        while self._viewer_layout.count():
            item = self._viewer_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        viewer = self._create_viewer(data, filename_hint, parser_display_name)
        if viewer is None:
            QMessageBox.warning(self, "No parser found", f"No parser could handle this data as {filename_hint!r}.")
            return

        self._viewer_layout.addWidget(viewer)

        if not self._viewer_pane.isVisible():
            self._viewer_pane.show()
            self.resize(self.width(), max(self.height() + 450, 750))

    def _create_viewer(self, data: bytes, filename_hint: str, parser_display_name: str | None) -> QWidget | None:
        import crush.parsers  # noqa: F401 — ensures all parsers are registered
        from crush.core.registry import ParserRegistry
        from crush.core.vfs import BytesVFS
        from crush.ui.viewer_factory import make_viewer

        if parser_display_name == "__hex__":
            from crush.viewers.hex_viewer import HexViewer
            return HexViewer(data, self)

        vfs = BytesVFS(data, name=filename_hint)
        node = vfs.root()

        if parser_display_name is None:
            parser = ParserRegistry.best(node, vfs)
        else:
            parser = next(
                (p for p in ParserRegistry._parsers if p.DISPLAY_NAME == parser_display_name),
                None,
            ) or ParserRegistry.best(node, vfs)

        if parser is None:
            return None

        try:
            result = parser.parse(node, vfs)
            return make_viewer(result, node, vfs, self)
        except Exception as exc:
            QMessageBox.warning(self, "Parse error", str(exc))
            return None
