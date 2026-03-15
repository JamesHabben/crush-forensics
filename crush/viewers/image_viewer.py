# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Image viewer — displays image files with fit-to-window scaling."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class ImageViewer(QWidget):
    """Viewer for image files (JPEG, PNG, HEIC via Qt, etc.)."""

    def __init__(self, data: bytes, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._raw = data
        self._build_ui()
        self._load(data)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setWidgetResizable(False)

        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self._scroll.setWidget(self._image_label)
        layout.addWidget(self._scroll)

    def _load(self, data: bytes) -> None:
        pixmap = QPixmap()
        loaded = pixmap.loadFromData(data)
        if not loaded:
            self._image_label.setText("Unable to decode image.")
            return

        # Scale to fit window while preserving aspect ratio
        scaled = pixmap.scaled(
            800, 600,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        # Re-scale on window resize
        self._load(self._raw)
