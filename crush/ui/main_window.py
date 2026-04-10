# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Crush main window — QMainWindow with dockable panels."""
from __future__ import annotations

from datetime import datetime, timezone
import time
import os
import subprocess
import sys
from pathlib import Path
import logging
import shutil
import tempfile

from PySide6.QtCore import QObject, QThread, Qt, Signal, QUrl, QSettings, QTimer
from PySide6.QtGui import QCloseEvent, QDesktopServices, QPalette, QColor, QAction
from shiboken6 import isValid
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QStatusBar,
    QTabBar,
    QTabWidget,
    QTextEdit,
    QWidget,
    QHBoxLayout,
    QPushButton,
)

import crush
from crush.core.vfs import VFS, VFSNode, DirectoryVFS
from crush.parsers.base import ParseResult
from crush.core.session import Session
from crush.ui.fs_panel import FilesystemPanel
from crush.ui.props_panel import PropertiesPanel
from crush.ui.loading_dialog import LoadingDialog


class _LoadSourceWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, session: Session, path: str, forensic: bool) -> None:
        super().__init__()
        self._session = session
        self._path = path
        self._forensic = forensic

    def run(self) -> None:
        try:
            vfs = self._session.add_source(self._path)
            if self._forensic:
                self._log_source_hash()
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(vfs)

    def _log_source_hash(self) -> None:
        path = Path(self._path)
        if not path.is_file():
            return
        import hashlib

        hasher = hashlib.sha256()
        total = 0
        with path.open("rb") as src:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
                total += len(chunk)
        digest = hasher.hexdigest()
        logging.getLogger("crush").info(
            "FORENSIC source sha256=%s  size=%d  path=%s", digest, total, path
        )


class _ClosableTabBar(QTabBar):
    def mouseReleaseEvent(self, event: object) -> None:  # type: ignore[override]
        if hasattr(event, "button") and event.button() == Qt.MouseButton.MiddleButton:
            index = self.tabAt(event.position().toPoint())
            if index >= 0:
                self.tabCloseRequested.emit(index)
                return
        super().mouseReleaseEvent(event)  # type: ignore[arg-type]


class _LogSignalHandler(QObject, logging.Handler):
    log_line = Signal(str)

    def __init__(self) -> None:
        QObject.__init__(self)
        logging.Handler.__init__(self)

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self.log_line.emit(msg)


class _DockTitleBar(QWidget):
    def __init__(self, title: str, dock: QDockWidget) -> None:
        super().__init__(dock)
        self._dock = dock
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)
        label = QLabel(title)
        layout.addWidget(label)
        layout.addStretch()
        dock_btn = QPushButton("Dock")
        dock_btn.setFixedHeight(20)
        dock_btn.clicked.connect(self._dock_back)
        layout.addWidget(dock_btn)

    def mousePressEvent(self, event: object) -> None:  # type: ignore[override]
        if hasattr(event, "button") and event.button() == Qt.MouseButton.LeftButton:
            if self._dock.isFloating() and self._dock.windowHandle() is not None:
                self._dock.windowHandle().startSystemMove()
                return
        super().mousePressEvent(event)  # type: ignore[arg-type]

    def _dock_back(self) -> None:
        mw = self._dock.parent()
        if hasattr(mw, "_dock_to_default"):
            mw._dock_to_default(self._dock)  # type: ignore[attr-defined]


class _ClickableStatusLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event: object) -> None:  # type: ignore[override]
        if hasattr(event, "button") and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            return
        super().mousePressEvent(event)  # type: ignore[arg-type]


class _ExportWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, vfs: VFS, node: VFSNode, dest_dir: str, forensic: bool) -> None:
        super().__init__()
        self._vfs = vfs
        self._node = node
        self._dest_dir = Path(dest_dir)
        self._forensic = forensic
        self._hash_lines: list[str] = []
        self._hash_base: Path | None = None
        self._logger = logging.getLogger(__name__)

    def run(self) -> None:
        try:
            target_root = self._dest_dir / _safe_name(self._node.name or "export")
            self._hash_base = target_root if self._node.is_dir else target_root.parent
            if self._node.is_dir:
                self._export_dir(self._node, target_root)
            else:
                target_root.parent.mkdir(parents=True, exist_ok=True)
                self._export_file(self._node, target_root)
            self._write_hashes_file(target_root)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(str(target_root))

    def _export_dir(self, node: VFSNode, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        for child in node.children:
            child_target = target / _safe_name(child.name)
            if child.is_dir:
                self._export_dir(child, child_target)
            else:
                child_target.parent.mkdir(parents=True, exist_ok=True)
                self._export_file(child, child_target)

    def _export_file(self, node: VFSNode, target: Path) -> None:
        if not self._forensic:
            with self._vfs.open(node) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            return

        import hashlib

        hasher = hashlib.sha256()
        total = 0
        with self._vfs.open(node) as src, open(target, "wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
                hasher.update(chunk)
                total += len(chunk)
        digest = hasher.hexdigest()
        rel_path = target.name
        if self._hash_base is not None:
            try:
                rel_path = str(target.relative_to(self._hash_base))
            except Exception:
                rel_path = target.name
        self._hash_lines.append(f"{digest}  {total}  {rel_path}")
        self._logger.info("FORENSIC export sha256=%s  size=%d  path=%s", digest, total, target)

    def _write_hashes_file(self, target_root: Path) -> None:
        if not self._forensic or not self._hash_lines:
            return
        base = self._hash_base if self._hash_base is not None else target_root.parent
        hash_path = base / "crush-export-hashes.txt"
        hash_path.write_text("\n".join(self._hash_lines) + "\n", encoding="utf-8")


def _safe_name(name: str) -> str:
    cleaned = name.replace("/", "_").replace("\\", "_").strip()
    if cleaned in {"", ".", ".."}:
        return "_"
    return cleaned


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.session = Session()
        self._always_hex = False
        self._pending_open: tuple[VFSNode, VFS] | None = None
        self._load_queue: list[tuple[str, bool, bool]] = []
        self._settings = QSettings("Crush DFIR", "Crush")
        self.setWindowTitle(f"Crush {crush.display_version()}")
        self.resize(1280, 800)
        self._build_ui()
        self._setup_logging()
        self._apply_saved_theme()
        self._apply_saved_forensic_mode()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setDockOptions(
            QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AnimatedDocks
        )
        self._dock_defaults: dict[QDockWidget, Qt.DockWidgetArea] = {}
        # Center: tabbed viewer area
        self._viewer_tabs = QTabWidget()
        self._viewer_tabs.setTabBar(_ClosableTabBar())
        self._viewer_tabs.setTabsClosable(True)
        self._viewer_tabs.setDocumentMode(True)
        self._viewer_tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self._viewer_tabs)

        # Left dock: filesystem panel
        self._fs_panel = FilesystemPanel(self.session, self)
        self._fs_panel.node_activated.connect(self._open_node)
        self._fs_panel.node_selected.connect(self._on_node_selected)
        self._fs_panel.open_requested.connect(self._open_node_mode)
        self._fs_panel.open_external_requested.connect(self._open_external_mode)
        self._fs_panel.export_requested.connect(self._export_node)
        self._fs_panel.close_source_requested.connect(self._close_source)
        self._fs_panel.background_status.connect(self._on_background_status)
        self._fs_panel.format_info_requested.connect(self._show_format_info)
        self._fs_dock = QDockWidget("Filesystem", self)
        self._fs_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self._fs_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self._fs_dock.setWidget(self._fs_panel)
        self._fs_dock.setMinimumWidth(220)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._fs_dock)
        self._dock_defaults[self._fs_dock] = Qt.DockWidgetArea.LeftDockWidgetArea
        self._fs_dock.topLevelChanged.connect(
            lambda floating, dock=self._fs_dock: self._sync_dock_titlebar(dock, floating)
        )

        # Right dock: properties panel
        self._props_panel = PropertiesPanel(self)
        self._props_dock = QDockWidget("Properties", self)
        self._props_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self._props_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self._props_dock.setWidget(self._props_panel)
        self._props_dock.setMinimumWidth(200)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._props_dock)
        self._dock_defaults[self._props_dock] = Qt.DockWidgetArea.RightDockWidgetArea
        self._props_dock.topLevelChanged.connect(
            lambda floating, dock=self._props_dock: self._sync_dock_titlebar(dock, floating)
        )

        # Bottom dock: log panel
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_dock = QDockWidget("Log", self)
        self._log_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self._log_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self._log_dock.setWidget(self._log_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._log_dock)
        self._dock_defaults[self._log_dock] = Qt.DockWidgetArea.BottomDockWidgetArea
        self._log_dock.hide()
        self._log_dock.topLevelChanged.connect(
            lambda floating, dock=self._log_dock: self._sync_dock_titlebar(dock, floating)
        )

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage(f"Crush {crush.display_version()} — ready")
        self._spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self._spinner_idx = 0
        self._spinner_label = QLabel("")
        self._spinner_label.setVisible(False)
        self._status.addPermanentWidget(self._spinner_label)
        self._bg_status = QLabel("")
        self._bg_status.setVisible(False)
        self._status.addPermanentWidget(self._bg_status)
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(100)
        self._spinner_timer.timeout.connect(self._on_spinner_tick)

        self._forensic_label = _ClickableStatusLabel(" \u2696 FORENSIC ")
        self._forensic_label.setStyleSheet(
            "color: white; background-color: #c87000; font-weight: bold;"
            " padding: 1px 4px; border-radius: 3px;"
        )
        self._forensic_label.setToolTip("Forensic mode active \u2014 files are hashed on open")
        self._forensic_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._forensic_label.clicked.connect(self._toggle_forensic_mode)
        self._forensic_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._forensic_label.customContextMenuRequested.connect(self._show_forensic_menu)
        self._forensic_label.setVisible(False)
        self._status.addPermanentWidget(self._forensic_label)
        self._nonforensic_label = _ClickableStatusLabel(" NON-FORENSIC ")
        self._nonforensic_label.setStyleSheet(
            "color: white; background-color: #6b6b6b; font-weight: bold;"
            " padding: 1px 4px; border-radius: 3px;"
        )
        self._nonforensic_label.setToolTip("Forensic mode is off")
        self._nonforensic_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._nonforensic_label.clicked.connect(self._toggle_forensic_mode)
        self._nonforensic_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._nonforensic_label.customContextMenuRequested.connect(self._show_forensic_menu)
        self._nonforensic_label.setVisible(True)
        self._status.addPermanentWidget(self._nonforensic_label)

        self._build_menus()

    def _build_menus(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("File")
        file_menu.addAction("Open file…", self._open_file)
        file_menu.addAction("Open ZIP archive…", self._open_zip)
        file_menu.addAction("Open TAR archive…", self._open_tar)
        file_menu.addAction("Open folder…", self._open_folder)
        file_menu.addSeparator()
        exit_action = file_menu.addAction("Exit", self.close)
        exit_action.setShortcut("Ctrl+Q")

        view_menu = menu.addMenu("View")
        view_menu.addAction(self._fs_dock.toggleViewAction())
        view_menu.addAction(self._props_dock.toggleViewAction())
        view_menu.addAction(self._log_dock.toggleViewAction())
        view_menu.addSeparator()
        view_menu.addAction("Dock Filesystem Panel", lambda: self._dock_to_default(self._fs_dock))
        view_menu.addAction("Dock Properties Panel", lambda: self._dock_to_default(self._props_dock))
        view_menu.addAction("Dock Log Panel", lambda: self._dock_to_default(self._log_dock))
        view_menu.addAction("Reset Panel Layout", self._reset_panel_layout)
        self._always_hex_action = QAction("Always show Hex tab", self, checkable=True)
        self._always_hex_action.toggled.connect(self._set_always_hex)
        view_menu.addAction(self._always_hex_action)
        view_menu.addAction("Close all tabs", self._close_all_tabs)

        tools_menu = menu.addMenu("Tools")
        tools_menu.addAction("Export log…", self._export_log)
        theme_menu = tools_menu.addMenu("Theme")
        theme_menu.addAction("System default", self._set_theme_system)
        theme_menu.addAction("Light", self._set_theme_light)
        theme_menu.addAction("Dark", self._set_theme_dark)
        tools_menu.addSeparator()
        self._forensic_mode_action = QAction("Forensic Mode", self, checkable=True)
        self._forensic_mode_action.setToolTip("Hash every file on open and write hash to log")
        self._forensic_mode_action.toggled.connect(self._set_forensic_mode)
        tools_menu.addAction(self._forensic_mode_action)

        help_menu = menu.addMenu("Help")
        help_menu.addAction("Format Reference…", self._show_format_reference)
        help_menu.addSeparator()
        help_menu.addAction("About Crush", self._about)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _open_zip(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open ZIP extraction", "", "ZIP archives (*.zip);;All files (*)"
        )
        if path:
            self._load_source(path)
    
    def _open_tar(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open TAR archive",
            "",
            "TAR archives (*.tar *.tar.gz *.tgz *.tar.bz2 *.tbz2 *.tar.xz *.txz);;All files (*)",
        )
        if path:
            self._load_source(path)

    def _open_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open folder")
        if path:
            self._load_source(path)

    def _open_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Open file", "", "All files (*)")
        for path in paths:
            self._load_source(path, open_after_load=True, append_to_tree=True)

    def _load_source(self, path: str, open_after_load: bool = False, append_to_tree: bool = False) -> None:
        if self._thread_is_running(getattr(self, "_load_thread", None)):
            self._load_queue.append((path, open_after_load, append_to_tree))
            self._status.showMessage("Queued source for loading…")
            self._logger.debug("Load queued: %s (open_after_load=%s append=%s)", path, open_after_load, append_to_tree)
            return

        self._logger.info("Loading source: %s", path)
        self._logger.debug("Load start: %s (open_after_load=%s append=%s)", path, open_after_load, append_to_tree)
        self._loading_path = path
        self._open_after_load = open_after_load
        self._append_to_tree = append_to_tree
        self._tree_build_started = time.monotonic()
        self._status.showMessage(f"Loading: {path}")
        self._progress = LoadingDialog("Loading source…", self)
        self._progress.show()

        self._load_thread = QThread(self)
        self._load_worker = _LoadSourceWorker(self.session, path, self.session.forensic_mode)
        self._load_worker.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.finished.connect(self._on_load_finished)
        self._load_worker.failed.connect(self._on_load_failed)
        self._load_worker.finished.connect(self._load_thread.quit)
        self._load_worker.failed.connect(self._load_thread.quit)
        self._load_thread.finished.connect(self._load_worker.deleteLater)
        self._load_thread.finished.connect(self._on_load_thread_finished)
        self._load_thread.start()

    def _on_load_finished(self, vfs: VFS) -> None:
        self._logger.debug("Load worker finished; preparing tree build")
        if hasattr(self, "_progress"):
            self._progress.set_text("Building tree…")
        if getattr(self, "_open_after_load", False) and not vfs.root().is_dir:
            self._pending_open = (vfs.root(), vfs)
        if getattr(self, "_tree_loaded_connected", False):
            try:
                self._fs_panel.load_finished.disconnect(self._on_tree_loaded)
            except Exception:
                pass
            self._tree_loaded_connected = False
        self._fs_panel.load_finished.connect(self._on_tree_loaded)
        self._tree_loaded_connected = True
        self._loading_vfs = vfs
        self._tree_loaded = False
        self._logger.debug("Dispatching to FilesystemPanel (%s)", "append" if getattr(self, "_append_to_tree", False) else "load")
        if getattr(self, "_append_to_tree", False):
            self._fs_panel.append_vfs(vfs)
        else:
            self._fs_panel.load_vfs(vfs)
        QTimer.singleShot(0, self._ensure_tree_loaded)

    def _on_load_failed(self, message: str) -> None:
        self._logger.debug("Load worker failed: %s", message)
        if hasattr(self, "_progress"):
            self._progress.close()
        self._status.showMessage(f"Error loading source: {message}")
        self._logger.error("Load error: %s", message)
        QMessageBox.critical(self, "Load error", message)

    def _on_tree_loaded(self) -> None:
        self._logger.debug("Tree load finished")
        self._tree_loaded = True
        if getattr(self, "_tree_loaded_connected", False):
            try:
                self._fs_panel.load_finished.disconnect(self._on_tree_loaded)
            except Exception:
                pass
            self._tree_loaded_connected = False
        if hasattr(self, "_progress"):
            self._progress.close()
        self._status.showMessage(f"Loaded: {self._loading_path}")
        self._logger.info("Loaded: %s", self._loading_path)
        if hasattr(self, "_tree_build_started"):
            elapsed = time.monotonic() - self._tree_build_started
            if hasattr(self, "_loading_vfs"):
                root = self._loading_vfs.root()
                try:
                    file_count = self._loading_vfs.file_count(root)
                    total_size = self._loading_vfs.total_size(root)
                    self._logger.info(
                        "Load + initial tree render: %.3f s (files: %s, size: %s)",
                        elapsed,
                        f"{file_count:,}",
                        _format_size(total_size),
                    )
                except Exception:
                    self._logger.info("Load + initial tree render: %.3f s", elapsed)
            else:
                self._logger.info("Load + initial tree render: %.3f s", elapsed)
        if self._pending_open:
            node, vfs = self._pending_open
            self._pending_open = None
            self._open_node(node, vfs)

    def _ensure_tree_loaded(self) -> None:
        if not getattr(self, "_tree_loaded", False):
            self._logger.warning("Tree load signal not received; closing progress dialog.")
            self._on_tree_loaded()

    def _export_node(self, node: VFSNode, vfs: VFS) -> None:
        dest_dir = QFileDialog.getExistingDirectory(self, "Export to folder")
        if not dest_dir:
            return

        if self._thread_is_running(getattr(self, "_export_thread", None)):
            QMessageBox.information(self, "Export", "An export is already running.")
            return

        self._status.showMessage("Exporting…")
        self._logger.info("Export requested: %s -> %s", node.path, dest_dir)
        self._export_progress = QProgressDialog("Exporting…", None, 0, 0, self)
        self._export_progress.setWindowTitle("Export")
        self._export_progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._export_progress.setCancelButton(None)
        self._export_progress.setMinimumDuration(0)
        self._export_progress.show()

        self._export_thread = QThread(self)
        self._export_worker = _ExportWorker(vfs, node, dest_dir, self.session.forensic_mode)
        self._export_worker.moveToThread(self._export_thread)
        self._export_thread.started.connect(self._export_worker.run)
        self._export_worker.finished.connect(self._on_export_finished)
        self._export_worker.failed.connect(self._on_export_failed)
        self._export_worker.finished.connect(self._export_thread.quit)
        self._export_worker.failed.connect(self._export_thread.quit)
        self._export_thread.finished.connect(self._export_worker.deleteLater)
        self._export_thread.finished.connect(self._on_export_thread_finished)
        self._export_thread.start()

    def _on_export_finished(self, dest: str) -> None:
        if hasattr(self, "_export_progress"):
            self._export_progress.close()
        self._status.showMessage(f"Exported to: {dest}")
        self._logger.info("Exported to: %s", dest)
        choice = QMessageBox.question(
            self,
            "Export complete",
            f"Export finished:\n{dest}\n\nOpen location?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if choice == QMessageBox.StandardButton.Yes:
            target = Path(dest)
            open_path = target.parent if target.is_file() else target
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(open_path)))

    def _on_export_failed(self, message: str) -> None:
        if hasattr(self, "_export_progress"):
            self._export_progress.close()
        self._status.showMessage(f"Export failed: {message}")
        self._logger.error("Export failed: %s", message)
        QMessageBox.critical(self, "Export failed", message)

    def _open_node(self, node: VFSNode, vfs: VFS) -> None:
        """Called when the user double-clicks a file in the FS panel."""
        self._hash_node_if_forensic(node, vfs)
        import crush.parsers  # noqa: F401 — triggers parser registration
        from crush.core.registry import ParserRegistry

        parser = ParserRegistry.best(node, vfs)
        if parser is None:
            self._status.showMessage(f"No parser found for {node.name}")
            return

        try:
            result = parser.parse(node, vfs)
            result = self._enrich_with_format_info(parser, node, vfs, result)
            self._show_result(node, result, vfs)
            self._props_panel.update_properties(node, result.metadata)
            self._status.showMessage(
                f"{node.path}  [{parser.DISPLAY_NAME}]"
            )
        except Exception as exc:
            self._status.showMessage(f"Parse error: {exc}")
            QMessageBox.warning(self, "Parse error", str(exc))

    def _open_node_mode(self, node: VFSNode, vfs: VFS, mode: str) -> None:
        if mode == "hex":
            self._hash_node_if_forensic(node, vfs)
            from crush.parsers.base import ParseResult
            hex_bytes = self._read_hex_bytes(vfs, node)
            if hex_bytes is None:
                QMessageBox.warning(self, "Hex view", "Unable to load hex view.")
                return
            result = ParseResult(viewer_type="hex", data=hex_bytes)
            result = self._enrich_with_format_info(None, node, vfs, result)
            self._show_result(node, result, vfs)
            self._props_panel.update_properties(node, result.metadata)
            return
        if mode == "text":
            self._hash_node_if_forensic(node, vfs)
            from crush.parsers.base import ParseResult
            raw = vfs.read(node)
            try:
                text = raw.decode("utf-8")
            except Exception:
                text = raw.decode("utf-8", errors="replace")
            result = ParseResult(viewer_type="text", data=text)
            result = self._enrich_with_format_info(None, node, vfs, result)
            self._show_result(node, result, vfs)
            self._props_panel.update_properties(node, result.metadata)
            return
        if mode == "multi_log":
            self._hash_node_if_forensic(node, vfs)
            from crush.parsers.base import ParseResult
            result = ParseResult(viewer_type="multi_log", data=None)
            self._show_result(node, result, vfs)
            self._status.showMessage(f"{node.path}  [Multi-Log Studio — loading…]")
            return
        if mode == "multi_log_add":
            self._hash_node_if_forensic(node, vfs)
            viewer = self._find_multi_log_viewer()
            if viewer is not None:
                viewer.add_source(node, vfs)
                self._status.showMessage(f"Added to Multi-Log Studio: {node.path}")
            else:
                # No open studio — open a new one
                from crush.parsers.base import ParseResult
                result = ParseResult(viewer_type="multi_log", data=None)
                self._show_result(node, result, vfs)
                self._status.showMessage(f"{node.path}  [Multi-Log Studio — loading…]")
            return
        if mode == "protobuf":
            self._hash_node_if_forensic(node, vfs)
            from crush.parsers.protobuf_parser import ProtobufParser
            parser = ProtobufParser()
            try:
                result = parser.parse(node, vfs)
                result = self._enrich_with_format_info(parser, node, vfs, result)
                self._show_result(node, result, vfs)
                self._props_panel.update_properties(node, result.metadata)
                self._status.showMessage(
                    f"{node.path}  [{parser.DISPLAY_NAME}]"
                )
            except Exception as exc:
                self._status.showMessage(f"Protobuf parse error: {exc}")
                QMessageBox.warning(self, "Protobuf parse error", str(exc))
            return
        self._open_node(node, vfs)

    def _find_multi_log_viewer(self) -> QWidget | None:
        """Return an open MultiLogViewer, preferring the currently active tab.

        Handles the always-hex wrapper (outer QTabWidget containing the viewer
        as its first child) by checking the ``crush_viewer`` property on the
        tab-level widget and then unwrapping if needed.
        """
        from crush.viewers.multi_log_viewer import MultiLogViewer
        from PySide6.QtWidgets import QTabWidget as _QTabWidget

        def _unwrap(w: QWidget) -> MultiLogViewer | None:
            if isinstance(w, MultiLogViewer):
                return w
            if isinstance(w, _QTabWidget):
                first = w.widget(0)
                if isinstance(first, MultiLogViewer):
                    return first
            return None

        # Check the active tab first
        current = self._viewer_tabs.currentWidget()
        if current is not None and current.property("crush_viewer") == "multi_log":
            result = _unwrap(current)
            if result is not None:
                return result

        # Fall back to the most recently added multi_log tab
        for i in range(self._viewer_tabs.count() - 1, -1, -1):
            w = self._viewer_tabs.widget(i)
            if w is not None and w.property("crush_viewer") == "multi_log":
                result = _unwrap(w)
                if result is not None:
                    # Bring that tab to front so the user sees where the source lands
                    self._viewer_tabs.setCurrentIndex(i)
                    return result
        return None

    def _open_external_mode(self, node: VFSNode, vfs: VFS, mode: str) -> None:
        if node.is_dir:
            if isinstance(vfs, DirectoryVFS) and Path(node.path).exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(node.path))))
            else:
                QMessageBox.information(
                    self,
                    "Open External",
                    "Opening directories from archives is not supported yet.",
                )
            return
        path = self._materialize_node_for_external(node, vfs)
        if path is None:
            QMessageBox.warning(self, "Open External", "Unable to materialize file.")
            return
        if mode == "choose":
            self._open_external_with_app(path)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_bytes_as_artifact(self, data: bytes, name: str) -> None:
        """Open in-memory bytes (e.g. a BLOB cell) as a new tab using the best parser."""
        import crush.parsers  # noqa: F401 — triggers parser registration
        from crush.core.registry import ParserRegistry
        from crush.core.vfs import BytesVFS

        vfs = BytesVFS(data, name=name)
        node = vfs.root()
        parser = ParserRegistry.best(node, vfs)
        if parser is None:
            return
        try:
            result = parser.parse(node, vfs)
            self._show_result(node, result, vfs)
            self._props_panel.update_properties(node, result.metadata)
            self._status.showMessage(f"Opened artifact: {name}  [{parser.DISPLAY_NAME}]")
        except Exception as exc:
            self._status.showMessage(f"Artifact parse error: {exc}")
            QMessageBox.warning(self, "Parse error", str(exc))

    def _materialize_node_for_external(self, node: VFSNode, vfs: VFS) -> Path | None:
        try:
            if isinstance(vfs, DirectoryVFS) and Path(node.path).exists():
                return Path(node.path)
            if not hasattr(self, "_external_temp_paths"):
                self._external_temp_paths: list[Path] = []
            tmp_dir = Path(tempfile.mkdtemp(prefix="crush-open-"))
            suffix = node.extension or ""
            tmp_path = tmp_dir / (node.name or f"file{suffix}")
            with vfs.open(node) as src, open(tmp_path, "wb") as dst:
                dst.write(src.read())
            self._external_temp_paths.append(tmp_path)
            return tmp_path
        except Exception as exc:
            if hasattr(self, "_logger"):
                self._logger.error("Open external failed: %s", exc)
            return None

    def _open_external_with_app(self, path: Path) -> None:
        title = "Choose application"
        app_path, _ = QFileDialog.getOpenFileName(self, title, "", "Applications (*)")
        if not app_path:
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen([app_path, str(path)], close_fds=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", app_path, str(path)])
            else:
                subprocess.Popen([app_path, str(path)])
        except Exception as exc:
            QMessageBox.warning(self, "Open External", str(exc))

    def _on_node_selected(self, node: VFSNode, vfs: VFS) -> None:
        metadata: dict[str, str] = {
            "Type": "Directory" if node.is_dir else "File",
        }
        if node.is_dir:
            metadata["Files"] = f"{vfs.file_count(node):,}"
            metadata["Total size"] = _format_size(vfs.total_size(node))
        else:
            metadata["Size"] = _format_size(node.size)
        self._props_panel.update_properties(node, metadata)

    def _show_result(self, node: VFSNode, result: ParseResult, vfs: VFS) -> None:
        from crush.ui.viewer_factory import make_viewer
        base_view = make_viewer(result, node, vfs, self)
        if hasattr(base_view, "open_bytes_requested"):
            base_view.open_bytes_requested.connect(self._open_bytes_as_artifact)
        widget: QWidget = base_view
        if self._always_hex:
            hex_bytes = self._read_hex_bytes(vfs, node)
            if hex_bytes is not None:
                from crush.viewers.hex_viewer import HexViewer
                tabbed = QTabWidget()
                tabbed.addTab(base_view, "View")
                tabbed.addTab(HexViewer(hex_bytes, tabbed), "Hex")
                widget = tabbed
            else:
                tabbed = QTabWidget()
                tabbed.addTab(base_view, "View")
                tabbed.addTab(QLabel("Unable to load hex view."), "Hex")
                widget = tabbed

        label = node.path
        existing_idx = -1
        for i in range(self._viewer_tabs.count()):
            w = self._viewer_tabs.widget(i)
            if w is None:
                continue
            if w.property("crush_path") == node.path and w.property("crush_viewer") == result.viewer_type:
                existing_idx = i
                break
        if existing_idx >= 0:
            self._viewer_tabs.setCurrentIndex(existing_idx)
            return
        if result.viewer_type == "hex":
            label = f"{node.path} [Hex]"
        elif result.viewer_type == "multi_log":
            label = f"{node.path} [Multi-Log]"
        widget.setProperty("crush_path", node.path)
        widget.setProperty("crush_viewer", result.viewer_type)
        widget.setProperty("crush_vfs", vfs)
        idx = self._viewer_tabs.addTab(widget, label)
        self._viewer_tabs.setTabToolTip(idx, node.path)
        self._viewer_tabs.setCurrentIndex(idx)

    def _close_tab(self, index: int) -> None:
        self._viewer_tabs.removeTab(index)

    def _close_all_tabs(self) -> None:
        self._viewer_tabs.clear()

    def _close_tabs_for_vfs(self, vfs: VFS) -> int:
        closed = 0
        for i in range(self._viewer_tabs.count() - 1, -1, -1):
            w = self._viewer_tabs.widget(i)
            if w is None:
                continue
            if w.property("crush_vfs") is vfs:
                self._viewer_tabs.removeTab(i)
                closed += 1
        return closed

    def _close_source(self, vfs: VFS) -> None:
        closed_tabs = self._close_tabs_for_vfs(vfs)
        self._fs_panel.close_vfs(vfs)
        self.session.remove_source(vfs)
        name = vfs.root().name
        self._status.showMessage(f"Closed source: {name} ({closed_tabs} tabs closed)")

    def _enrich_with_format_info(self, parser: object, node: VFSNode, vfs: VFS, result: object) -> object:
        """Prepend format knowledge-base metadata to a ParseResult without overriding parser data."""
        try:
            from crush.core.format_db import FormatDatabase
            from crush.parsers.base import ParseResult
            fmt = FormatDatabase.get().by_parser_class(type(parser).__name__) if parser else None
            if fmt is None:
                peek = vfs.peek(node)
                fmt = FormatDatabase.get().identify(peek, node.name)
            if fmt is None:
                return result
            fmt_meta: dict = {"Format": fmt.name}
            if fmt.platforms:
                fmt_meta["Platforms"] = fmt.platforms.replace(",", ", ")
            if fmt.forensic_relevance:
                fmt_meta["Forensic relevance"] = fmt.forensic_relevance
            if fmt.links:
                fmt_meta["Reference"] = fmt.links[0][1]
            # Parser metadata takes precedence over format defaults
            merged = {**fmt_meta, **result.metadata}  # type: ignore[union-attr]
            return ParseResult(
                result.viewer_type,  # type: ignore[union-attr]
                result.data,  # type: ignore[union-attr]
                result.sub_nodes,  # type: ignore[union-attr]
                merged,
                result.text_index,  # type: ignore[union-attr]
            )
        except Exception:
            return result

    def _show_format_info(self, node: VFSNode, vfs: VFS) -> None:
        """Show a format info popup and also update the Properties panel."""
        try:
            from crush.core.format_db import FormatDatabase
            from crush.ui.format_info_dialog import FormatInfoDialog
            peek = vfs.peek(node)
            fmt = FormatDatabase.get().identify(peek, node.name)
            dlg = FormatInfoDialog(node, fmt, self)
            dlg.exec()
            # Also update the Properties panel
            if fmt:
                meta: dict = {"Format": fmt.name}
                if fmt.category:
                    meta["Category"] = fmt.category
                if fmt.platforms:
                    meta["Platforms"] = fmt.platforms.replace(",", ", ")
                if fmt.forensic_relevance:
                    meta["Forensic relevance"] = fmt.forensic_relevance
                meta["Parser support"] = "Supported" if fmt.parser_class else "Not yet supported"
                if fmt.links:
                    meta["Reference"] = fmt.links[0][1]
                self._props_panel.update_properties(node, meta)
                self._props_dock.show()
                self._props_dock.raise_()
        except Exception as exc:
            self._status.showMessage(f"Format info error: {exc}")

    def _show_format_reference(self) -> None:
        from crush.ui.format_reference import FormatReferenceDialog
        dlg = FormatReferenceDialog(self)
        dlg.exec()

    def _about(self) -> None:
        from crush.ui.about_dialog import AboutDialog
        AboutDialog(self).exec()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._status.showMessage("Closing…")
        if hasattr(self, "_logger"):
            self._logger.info("Closing application")

        if self._thread_is_running(getattr(self, "_load_thread", None)):
            self._load_thread.quit()
            self._load_thread.wait(2000)
        if self._thread_is_running(getattr(self, "_export_thread", None)):
            self._export_thread.quit()
            self._export_thread.wait(2000)

        try:
            self.session.close()
        except Exception as exc:
            if hasattr(self, "_logger"):
                self._logger.error("Error during shutdown: %s", exc)

        # Best-effort cleanup for temp files created for external open.
        for tmp_path in getattr(self, "_external_temp_paths", []):
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
                if tmp_path.parent.exists():
                    tmp_path.parent.rmdir()
            except Exception:
                pass

        event.accept()

    def _reset_panel_layout(self) -> None:
        for dock, area in (
            (self._fs_dock, Qt.DockWidgetArea.LeftDockWidgetArea),
            (self._props_dock, Qt.DockWidgetArea.RightDockWidgetArea),
            (self._log_dock, Qt.DockWidgetArea.BottomDockWidgetArea),
        ):
            try:
                self._dock_to_default(dock)
                dock.show()
            except Exception:
                continue

    def _on_spinner_tick(self) -> None:
        self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_chars)
        self._spinner_label.setText(self._spinner_chars[self._spinner_idx])

    def _on_background_status(self, text: str) -> None:
        if not text:
            self._spinner_timer.stop()
            self._spinner_label.setVisible(False)
            self._bg_status.setVisible(False)
            self._bg_status.setText("")
            self._bg_status.setToolTip("")
            return
        self._bg_status.setText(text)
        self._bg_status.setToolTip(text)
        self._bg_status.setVisible(True)
        self._spinner_label.setVisible(True)
        if not self._spinner_timer.isActive():
            self._spinner_timer.start()

    def _sync_dock_titlebar(self, dock: QDockWidget, floating: bool) -> None:
        if floating:
            dock.setTitleBarWidget(_DockTitleBar(dock.windowTitle(), dock))
        else:
            dock.setTitleBarWidget(None)

    def _dock_to_default(self, dock: QDockWidget) -> None:
        area = self._dock_defaults.get(dock, Qt.DockWidgetArea.LeftDockWidgetArea)
        if dock.isFloating():
            dock.setFloating(False)
        self.addDockWidget(area, dock)

    def _thread_is_running(self, thread: QThread | None) -> bool:
        if thread is None:
            return False
        if not isValid(thread):
            return False
        try:
            return thread.isRunning()
        except RuntimeError:
            return False

    def _on_load_thread_finished(self) -> None:
        self._load_thread = None
        if self._load_queue:
            path, open_after_load, append_to_tree = self._load_queue.pop(0)
            self._load_source(path, open_after_load=open_after_load, append_to_tree=append_to_tree)

    def _on_export_thread_finished(self) -> None:
        self._export_thread = None

    def _setup_logging(self) -> None:
        self._logger = logging.getLogger("crush")
        level_name = os.getenv("CRUSH_LOG_LEVEL", "INFO").upper()
        level = logging.getLevelName(level_name)
        if not isinstance(level, int):
            level = logging.INFO
        self._logger.setLevel(level)
        self._log_level = level
        self._logger.propagate = False

        self._log_signal_handler = _LogSignalHandler()
        self._log_signal_handler.setLevel(level)
        self._log_signal_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        self._log_signal_handler.log_line.connect(self._append_log_line)
        self._logger.addHandler(self._log_signal_handler)

        self._file_handler: logging.FileHandler | None = None
        self._set_log_path(self._default_log_path())
        self._logger.info("Logging started: %s", self._log_path)

    def _default_log_path(self) -> Path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return Path(tempfile.gettempdir()) / f"crush-{ts}.log"

    def _set_log_path(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if self._file_handler:
            self._logger.removeHandler(self._file_handler)
            self._file_handler.close()
        self._file_handler = logging.FileHandler(path, encoding="utf-8")
        self._file_handler.setLevel(getattr(self, "_log_level", logging.INFO))
        self._file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        self._logger.addHandler(self._file_handler)
        self._log_path = path
        self._status.showMessage(f"Logging to: {path}")

    def _export_log(self) -> None:
        if not hasattr(self, "_log_path"):
            QMessageBox.information(self, "Export log", "No log file yet.")
            return
        suggested = self._log_path.name
        dest_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export log",
            suggested,
            "Log files (*.log);;All files (*)",
        )
        if not dest_path:
            return
        try:
            shutil.copy2(self._log_path, dest_path)
            self._status.showMessage(f"Log exported to: {dest_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export log failed", str(exc))

    def _append_log_line(self, line: str) -> None:
        self._log_view.append(line)

    def _set_theme_system(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app.setPalette(self.style().standardPalette())
        self._settings.setValue("theme", "system")
        self._logger.info("Theme set to system default")

    def _set_always_hex(self, enabled: bool) -> None:
        self._always_hex = enabled
        if hasattr(self, "_logger"):
            self._logger.info("Always show hex tab: %s", enabled)

    def _forensic_mode_description(self) -> str:
        return (
            "Forensic mode does the following:\n"
            "- Records SHA-256 hashes when files are opened or exported.\n"
            "- Hashes ZIP/TAR/file sources on open (folders are not hashed).\n"
            "- Writes those hashes to the log.\n"
            "- Creates a crush-export-hashes.txt file next to exported data.\n"
            "- You can turn it off for faster opening of large ZIP/TAR sources and faster browsing."
        )

    def _show_forensic_menu(self, pos: object) -> None:
        sender = self.sender()
        if sender is None or not hasattr(sender, "mapToGlobal"):
            return
        menu = QMenu(self)
        toggle_action = menu.addAction("Toggle Forensic Mode")
        info_action = menu.addAction("What is Forensic Mode?")
        action = menu.exec(sender.mapToGlobal(pos))  # type: ignore[arg-type]
        if action == toggle_action:
            self._toggle_forensic_mode()
        elif action == info_action:
            QMessageBox.information(self, "Forensic Mode", self._forensic_mode_description())

    def _toggle_forensic_mode(self) -> None:
        self._forensic_mode_action.setChecked(not self._forensic_mode_action.isChecked())

    def _set_forensic_mode(self, enabled: bool) -> None:
        self.session.forensic_mode = enabled
        self._forensic_label.setVisible(enabled)
        self._nonforensic_label.setVisible(not enabled)
        self._settings.setValue("forensic_mode", enabled)
        state = "enabled" if enabled else "disabled"
        if hasattr(self, "_logger"):
            self._logger.info("Forensic mode %s", state)

    def _hash_node_if_forensic(self, node: VFSNode, vfs: VFS) -> None:
        if not self.session.forensic_mode or node.is_dir:
            return
        import hashlib
        try:
            data = vfs.read(node)
            digest = hashlib.sha256(data).hexdigest()
            self._logger.info(
                "FORENSIC sha256=%s  size=%d  path=%s", digest, len(data), node.path
            )
        except Exception as exc:
            self._logger.warning("FORENSIC hash failed for %s: %s", node.path, exc)

    def _read_hex_bytes(self, vfs: VFS, node: VFSNode) -> bytes | None:
        max_bytes = 1024 * 256
        try:
            with vfs.open(node) as src:
                return src.read(max_bytes)
        except Exception as exc:
            if hasattr(self, "_logger"):
                self._logger.warning("Failed to read hex bytes for %s: %s", node.path, exc)
            return None

    def _set_theme_light(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app.setPalette(self._light_palette())
        self._settings.setValue("theme", "light")
        self._logger.info("Theme set to light")

    def _set_theme_dark(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app.setPalette(self._dark_palette())
        self._settings.setValue("theme", "dark")
        self._logger.info("Theme set to dark")

    def _light_palette(self) -> QPalette:
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor(248, 249, 251))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(25, 25, 25))
        pal.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(242, 244, 247))
        pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
        pal.setColor(QPalette.ColorRole.ToolTipText, QColor(0, 0, 0))
        pal.setColor(QPalette.ColorRole.Text, QColor(25, 25, 25))
        pal.setColor(QPalette.ColorRole.Button, QColor(240, 242, 245))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor(25, 25, 25))
        if hasattr(QPalette.ColorRole, "Menu"):
            pal.setColor(QPalette.ColorRole.Menu, QColor(248, 249, 251))
        if hasattr(QPalette.ColorRole, "MenuText"):
            pal.setColor(QPalette.ColorRole.MenuText, QColor(25, 25, 25))
        if hasattr(QPalette.ColorRole, "MenuBar"):
            pal.setColor(QPalette.ColorRole.MenuBar, QColor(248, 249, 251))
        if hasattr(QPalette.ColorRole, "MenuBarText"):
            pal.setColor(QPalette.ColorRole.MenuBarText, QColor(25, 25, 25))
        pal.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(56, 120, 255))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        return pal

    def _apply_saved_theme(self) -> None:
        theme = self._settings.value("theme", "light")
        if theme == "dark":
            self._set_theme_dark()
        elif theme == "system":
            self._set_theme_system()
        else:
            self._set_theme_light()

    def _apply_saved_forensic_mode(self) -> None:
        enabled = self._settings.value("forensic_mode", False, type=bool)
        # setChecked triggers the toggled signal which calls _set_forensic_mode
        self._forensic_mode_action.setChecked(enabled)

    def _dark_palette(self) -> QPalette:
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor(32, 34, 37))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
        pal.setColor(QPalette.ColorRole.Base, QColor(24, 26, 29))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(32, 34, 37))
        pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
        pal.setColor(QPalette.ColorRole.ToolTipText, QColor(0, 0, 0))
        pal.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
        pal.setColor(QPalette.ColorRole.Button, QColor(45, 48, 52))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
        if hasattr(QPalette.ColorRole, "Menu"):
            pal.setColor(QPalette.ColorRole.Menu, QColor(32, 34, 37))
        if hasattr(QPalette.ColorRole, "MenuText"):
            pal.setColor(QPalette.ColorRole.MenuText, QColor(220, 220, 220))
        if hasattr(QPalette.ColorRole, "MenuBar"):
            pal.setColor(QPalette.ColorRole.MenuBar, QColor(32, 34, 37))
        if hasattr(QPalette.ColorRole, "MenuBarText"):
            pal.setColor(QPalette.ColorRole.MenuBarText, QColor(220, 220, 220))
        pal.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(64, 128, 255))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
        return pal


def _format_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(size)
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(value)} {units[unit_index]}"
    return f"{value:.1f} {units[unit_index]}"
