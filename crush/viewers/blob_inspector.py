# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""BLOB Inspector dialog with a chainable decode pipeline."""
from __future__ import annotations

import base64
import json as _json
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QContextMenuEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from crush.core.formatters import (
    bytes_to_hexview,
    try_plist_text,
    try_xml_text,
)

# Column layout of bytes_to_hexview output, e.g. "0000000a: 48 65 6c  Hel"
_BLOB_HEX_START = 10
_BLOB_HEX_END = 57
_BLOB_ASCII_START = 59

_PROTOBUF_INTERP_SKIP = {"uint64", "uint32"}


# ---------------------------------------------------------------------------
# Decode functions — intermediate (bytes → bytes)
# ---------------------------------------------------------------------------

def _decode_base64(data: bytes) -> bytes | None:
    try:
        return base64.b64decode(data.strip())
    except Exception:
        return None


def _decode_hex(data: bytes) -> bytes | None:
    try:
        text = data.decode("ascii", errors="ignore")
        cleaned = "".join(text.split()).replace(":", "")
        return bytes.fromhex(cleaned)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Render functions — terminal (bytes → str)
# ---------------------------------------------------------------------------

def _try_utf8(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except Exception:
        return ""


def _try_latin1(data: bytes) -> str:
    try:
        return data.decode("latin-1")
    except Exception:
        return ""


def _try_json(data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except Exception:
        return ""
    unescaped = text.replace('\\"', '"')
    for candidate in (text, unescaped):
        try:
            return _json.dumps(_json.loads(candidate), indent=2, ensure_ascii=False)
        except Exception:
            pass
    candidate = unescaped if '\\"' in text else text
    if candidate.lstrip().startswith(("{", "[")):
        return "[partial / truncated JSON — pretty-print not possible]\n\n" + candidate
    return ""


def _try_plist(data: bytes) -> str:
    return try_plist_text(data) or ""


def _try_xml(data: bytes) -> str:
    return try_xml_text(data) or ""


def _try_protobuf(data: bytes) -> str:
    try:
        from crush.parsers.protobuf_parser import _decode_message
        decoded, warning, _text = _decode_message(data)
        result = _render_protobuf(decoded.get("entries", []))
        if warning:
            result = f"# Warning: {warning}\n\n{result}"
        return result
    except Exception:
        return ""


def _try_abx(data: bytes) -> str:
    try:
        from crush.parsers.abx_decoder import decode_abx
        return decode_abx(data).xml
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Format registries — add a new format by adding one entry here
# ---------------------------------------------------------------------------

# bytes → bytes; None on failure
_INTERMEDIATE: dict[str, Callable[[bytes], bytes | None]] = {
    "Base64 (decode)":  _decode_base64,
    "Hex → Bytes":      _decode_hex,
}

# bytes → str; tuple is (render_fn, error_label_on_failure)
_TERMINAL_TEXT: dict[str, tuple[Callable[[bytes], str], str]] = {
    "UTF-8 text":               (_try_utf8,     "[decode error]"),
    "Latin-1 text":             (_try_latin1,   "[decode error]"),
    "JSON":                     (_try_json,     "[parse error]"),
    "Plist / bplist":           (_try_plist,    "[parse error]"),
    "XML":                      (_try_xml,      "[parse error]"),
    "Protobuf (schema-less)":   (_try_protobuf, "[parse error]"),
    "Android Binary XML (ABX)": (_try_abx,      "[parse error]"),
}

# Subset of _TERMINAL_TEXT keys tried in order by "Auto"
_AUTO_ORDER: tuple[str, ...] = (
    "Plist / bplist",
    "XML",
    "JSON",
    "UTF-8 text",
    "Latin-1 text",
)

# Derived tuples for combo boxes — "Auto" / "Hex view" / "Image" stay special
_INTERMEDIATE_FORMATS: tuple[str, ...] = tuple(_INTERMEDIATE)
_TERMINAL_FORMATS: tuple[str, ...] = (
    "Auto",
    "Hex view",
    *_TERMINAL_TEXT,
    "Image (PNG / JPEG / GIF)",
)
_ALL_FORMATS: tuple[str, ...] = _TERMINAL_FORMATS + _INTERMEDIATE_FORMATS


def _is_image(data: bytes) -> bool:
    return (
        data[:8] == b"\x89PNG\r\n\x1a\n"
        or data[:3] == b"\xff\xd8\xff"
        or data[:6] in (b"GIF87a", b"GIF89a")
    )


def _render_protobuf(entries: list, indent: int = 0) -> str:
    lines: list[str] = []
    pad = "  " * indent
    ipad = pad + "    "
    for entry in entries:
        field = entry.get("field", "?")
        wt = entry.get("wire_type", "?")
        val = entry.get("value")
        interpretations = [
            i for i in entry.get("interpretations", [])
            if i.label not in _PROTOBUF_INTERP_SKIP
        ]
        if isinstance(val, dict):
            vtype = val.get("type")
            if vtype == "message":
                lines.append(f"{pad}{field} {{")
                lines.append(_render_protobuf(val.get("entries", []), indent + 1))
                lines.append(f"{pad}}}")
            elif vtype == "string":
                lines.append(f'{pad}{field}: "{val.get("text", "")}"')
            else:
                lines.append(f"{pad}{field}: <{val.get('hex_preview', '')}>")
        elif isinstance(val, bytes):
            lines.append(f"{pad}{field}: {val[:32].hex()}" + ("…" if len(val) > 32 else ""))
        else:
            lines.append(f"{pad}{field} [{wt}]: {val}")
        for interp in interpretations:
            lines.append(f"{ipad}# {interp.label}: {interp.value}")
    return "\n".join(lines)


class _BlobViewerEdit(QPlainTextEdit):
    """QPlainTextEdit with a hex-aware context menu."""

    def __init__(self, inspector: "BlobInspector") -> None:
        super().__init__()
        self._inspector = inspector

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = self.createStandardContextMenu()
        cursor = self.textCursor()
        if cursor.hasSelection() and self._inspector._is_hex_mode():
            menu.addSeparator()
            menu.addAction("Copy Selected Hex").triggered.connect(
                self._inspector._copy_selected_hex
            )
            menu.addAction("Copy Selected ASCII").triggered.connect(
                self._inspector._copy_selected_ascii
            )
        menu.addSeparator()
        menu.addAction("Copy All").triggered.connect(self._inspector._copy_all)
        menu.exec(event.globalPos())


class _StepRow(QWidget):
    """One row in the decode pipeline: step label + format combo + size hint + remove button."""

    def __init__(
        self,
        number: int,
        formats: tuple[str, ...],
        inspector: "BlobInspector",
    ) -> None:
        super().__init__()
        self._inspector = inspector

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(4)

        self._num_label = QLabel(f"Step {number}:")
        row.addWidget(self._num_label)

        self._combo = QComboBox()
        self._combo.blockSignals(True)
        self._combo.addItems(formats)
        self._combo.blockSignals(False)
        self._combo.currentIndexChanged.connect(self._on_changed)
        row.addWidget(self._combo, stretch=1)

        self._hint = QLabel("")
        self._hint.setStyleSheet("color: gray;")
        self._hint.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row.addWidget(self._hint)

        self._remove_btn = QPushButton("✕")
        self._remove_btn.setFixedWidth(28)
        self._remove_btn.setToolTip("Remove this step")
        self._remove_btn.clicked.connect(lambda: self._inspector._remove_step(self))
        row.addWidget(self._remove_btn)

    def format(self) -> str:
        return self._combo.currentText()

    def is_intermediate(self) -> bool:
        return self.format() in _INTERMEDIATE_FORMATS

    def set_number(self, n: int) -> None:
        self._num_label.setText(f"Step {n}:")

    def set_hint(self, text: str) -> None:
        self._hint.setText(text)

    def show_remove(self, visible: bool) -> None:
        self._remove_btn.setVisible(visible)

    def _on_changed(self) -> None:
        self._inspector._on_step_format_changed(self)


class BlobInspector(QDialog):
    def __init__(
        self,
        blob: bytes,
        parent: QWidget | None = None,
        *,
        display_text: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._blob = blob
        self._display_text = display_text
        self._steps: list[_StepRow] = []
        self._hex_mode = False
        self._build_ui()
        self._push_step(first=True)

    def _build_ui(self) -> None:
        self.setWindowTitle(f"BLOB Inspector ({len(self._blob):,} B)")
        self.resize(700, 500)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        pipeline_container = QWidget()
        self._pipeline_layout = QVBoxLayout(pipeline_container)
        self._pipeline_layout.setContentsMargins(0, 0, 0, 0)
        self._pipeline_layout.setSpacing(0)
        outer.addWidget(pipeline_container)

        self._add_btn = QPushButton("＋  Add decode step")
        self._add_btn.setVisible(False)
        self._add_btn.clicked.connect(lambda: self._push_step(first=False))
        outer.addWidget(self._add_btn)

        self._stack = QStackedWidget()

        self._viewer = _BlobViewerEdit(self)
        self._viewer.setReadOnly(True)
        self._viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._stack.addWidget(self._viewer)

        self._img_scroll = QScrollArea()
        self._img_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_scroll.setWidgetResizable(False)
        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_scroll.setWidget(self._img_label)
        self._stack.addWidget(self._img_scroll)

        outer.addWidget(self._stack, stretch=1)

        bottom = QHBoxLayout()
        self._copy_btn = QPushButton("Copy")
        self._copy_btn.clicked.connect(self._copy_current)
        bottom.addWidget(self._copy_btn)
        bottom.addStretch()
        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.reject)
        bottom.addWidget(close_box)
        outer.addLayout(bottom)

    def _first_step_formats(self) -> tuple[str, ...]:
        if self._display_text is not None:
            return ("Decoded (from table)",) + _ALL_FORMATS
        return _ALL_FORMATS

    def _push_step(self, *, first: bool) -> None:
        number = len(self._steps) + 1
        formats = self._first_step_formats() if first else _ALL_FORMATS
        step = _StepRow(number, formats, self)
        step.show_remove(not first)
        self._steps.append(step)
        self._pipeline_layout.addWidget(step)
        self._recompute()

    def _remove_step(self, step: _StepRow) -> None:
        idx = self._steps.index(step)
        self._steps.pop(idx)
        self._pipeline_layout.removeWidget(step)
        step.deleteLater()
        for i, s in enumerate(self._steps):
            s.set_number(i + 1)
        if self._steps:
            self._steps[0].show_remove(False)
        self._recompute()

    def _on_step_format_changed(self, step: _StepRow) -> None:
        idx = self._steps.index(step)
        # if a non-last step switched to terminal, drop all steps after it
        if idx < len(self._steps) - 1 and not step.is_intermediate():
            for s in self._steps[idx + 1:]:
                self._pipeline_layout.removeWidget(s)
                s.deleteLater()
            del self._steps[idx + 1:]
        self._recompute()

    def _recompute(self) -> None:
        if not self._steps:
            return
        current = self._blob

        for i, step in enumerate(self._steps):
            is_last = i == len(self._steps) - 1
            fmt = step.format()

            if step.is_intermediate():
                result = _INTERMEDIATE[fmt](current)
                if result is None:
                    step.set_hint("→ [error]")
                    for s in self._steps[i + 1:]:
                        s.set_hint("")
                    self._viewer.setPlainText(f"[step {i + 1}: {fmt!r} failed]")
                    self._stack.setCurrentIndex(0)
                    self._hex_mode = False
                    self._copy_btn.setEnabled(False)
                    self._add_btn.setVisible(False)
                    return
                step.set_hint(f"→ {len(result):,} B")
                if is_last:
                    self._hex_mode = True
                    self._viewer.setPlainText(bytes_to_hexview(result, max_bytes=200_000))
                    self._stack.setCurrentIndex(0)
                    self._copy_btn.setEnabled(True)
                    self._add_btn.setVisible(True)
                    return
                current = result
            else:
                step.set_hint("")
                self._render_final(fmt, current)
                self._add_btn.setVisible(False)
                return

    def _render_final(self, fmt: str, data: bytes) -> None:
        if fmt == "Decoded (from table)":
            self._stack.setCurrentIndex(0)
            self._hex_mode = False
            self._copy_btn.setEnabled(True)
            self._viewer.setPlainText(self._display_text or "")
            return

        if fmt == "Image (PNG / JPEG / GIF)":
            self._show_image(data)
            return

        if fmt == "Auto" and _is_image(data):
            self._show_image(data)
            return

        self._stack.setCurrentIndex(0)
        self._copy_btn.setEnabled(True)
        self._hex_mode = False

        if fmt == "Auto":
            for key in _AUTO_ORDER:
                content = _TERMINAL_TEXT[key][0](data)
                if content:
                    break
            else:
                content = bytes_to_hexview(data, max_bytes=200_000)
                self._hex_mode = True
        elif fmt == "Hex view":
            self._hex_mode = True
            content = bytes_to_hexview(data, max_bytes=200_000)
        elif fmt in _TERMINAL_TEXT:
            render_fn, error_label = _TERMINAL_TEXT[fmt]
            content = render_fn(data) or error_label
        else:
            content = ""
        self._viewer.setPlainText(content[:500_000])

    def _show_image(self, data: bytes) -> None:
        from PySide6.QtCore import QByteArray
        px = QPixmap()
        if px.loadFromData(QByteArray(data)):
            self._img_label.setPixmap(px)
            self._img_label.resize(px.size())
            self._stack.setCurrentIndex(1)
            self._copy_btn.setEnabled(False)
        else:
            self._stack.setCurrentIndex(0)
            self._copy_btn.setEnabled(True)
            self._viewer.setPlainText("[not a recognised image format]")

    def _is_hex_mode(self) -> bool:
        return self._hex_mode

    def _copy_current(self) -> None:
        QApplication.clipboard().setText(self._viewer.toPlainText())

    def _copy_all(self) -> None:
        QApplication.clipboard().setText(self._viewer.toPlainText())

    def _copy_selected_hex(self) -> None:
        cursor = self._viewer.textCursor()
        if not cursor.hasSelection():
            return
        tokens: list[str] = []
        for line in cursor.selectedText().split(" "):
            hex_section = line[_BLOB_HEX_START:_BLOB_HEX_END]
            for part in hex_section.split():
                if len(part) == 2 and all(c in "0123456789ABCDEFabcdef" for c in part):
                    tokens.append(part.upper())
        QApplication.clipboard().setText(" ".join(tokens))

    def _copy_selected_ascii(self) -> None:
        cursor = self._viewer.textCursor()
        if not cursor.hasSelection():
            return
        parts: list[str] = []
        for line in cursor.selectedText().split(" "):
            if len(line) > _BLOB_ASCII_START:
                parts.append(line[_BLOB_ASCII_START:])
        QApplication.clipboard().setText("".join(parts))
