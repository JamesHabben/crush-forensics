# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Media viewer — audio and video playback via Qt Multimedia."""
from __future__ import annotations

import os
import tempfile

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QCloseEvent
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class MediaViewer(QWidget):
    """Viewer for video and audio files using Qt Multimedia."""

    def __init__(self, data: bytes, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tmp_path: str | None = None
        self._build_ui()
        self._load(data)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Video surface
        self._video_widget = QVideoWidget()
        layout.addWidget(self._video_widget, stretch=1)

        # Player + audio
        self._player = QMediaPlayer()
        self._audio = QAudioOutput()
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video_widget)
        self._audio.setVolume(0.8)

        # Controls
        controls = QWidget()
        controls.setFixedHeight(48)
        ctrl_layout = QHBoxLayout(controls)
        ctrl_layout.setContentsMargins(8, 4, 8, 4)
        ctrl_layout.setSpacing(8)

        self._play_btn = QPushButton("Play")
        self._play_btn.setFixedWidth(60)
        self._play_btn.clicked.connect(self._toggle_play)
        ctrl_layout.addWidget(self._play_btn)

        self._position_slider = QSlider(Qt.Orientation.Horizontal)
        self._position_slider.setRange(0, 0)
        self._position_slider.sliderMoved.connect(self._seek)
        ctrl_layout.addWidget(self._position_slider, stretch=1)

        self._time_label = QLabel("0:00 / 0:00")
        ctrl_layout.addWidget(self._time_label)

        layout.addWidget(controls)

        # Connect signals
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)

    def _load(self, data: bytes) -> None:
        # Write bytes to a temp file — QMediaPlayer needs a URL
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".media")
        tmp.write(data)
        tmp.close()
        self._tmp_path = tmp.name
        self._player.setSource(QUrl.fromLocalFile(self._tmp_path))

    def _toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _seek(self, position: int) -> None:
        self._player.setPosition(position)

    def _on_position_changed(self, position: int) -> None:
        self._position_slider.setValue(position)
        self._time_label.setText(
            f"{_ms_to_str(position)} / {_ms_to_str(self._player.duration())}"
        )

    def _on_duration_changed(self, duration: int) -> None:
        self._position_slider.setRange(0, duration)

    def _on_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._play_btn.setText("Pause")
        else:
            self._play_btn.setText("Play")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._player.stop()
        if self._tmp_path and os.path.exists(self._tmp_path):
            os.unlink(self._tmp_path)
        super().closeEvent(event)


def _ms_to_str(ms: int) -> str:
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"
