# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Filesystem panel — left dock, shows the VFS tree."""
from __future__ import annotations

from collections import deque

from PySide6.QtCore import QModelIndex, Qt, Signal, QSortFilterProxyModel, QTimer
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QLineEdit,
    QMenu,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from crush.core.session import Session
from crush.core.vfs import VFS, VFSNode

_ROLE_NODE = Qt.ItemDataRole.UserRole + 1
_ROLE_VFS  = Qt.ItemDataRole.UserRole + 2

# Extension → badge label (shown in the Type column)
_SQLITE_MAGIC = b"SQLite format 3\x00"
_BPLIST_MAGIC = b"bplist"
_XML_PLIST_SIG = b"<?xml"

_SIZE_UNITS: list[str] = ["B", "KB", "MB", "GB", "TB", "PB"]


def _format_size(size: int) -> str:
    value = float(size)
    unit_index = 0
    while value >= 1024 and unit_index < len(_SIZE_UNITS) - 1:
        value /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(value)} {_SIZE_UNITS[unit_index]}"
    return f"{value:.1f} {_SIZE_UNITS[unit_index]}"


class FilesystemPanel(QWidget):
    """Left-dock panel that displays the VFS as a tree."""

    node_activated = Signal(object, object)  # (VFSNode, VFS)
    node_selected = Signal(object, object)  # (VFSNode, VFS)
    open_requested = Signal(object, object, str)  # (VFSNode, VFS, mode)
    export_requested = Signal(object, object)  # (VFSNode, VFS)
    load_finished = Signal()

    def __init__(self, session: Session, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels(["Name", "Size", "Files", "Total Size", "Type"])
        self._proxy = _VfsFilterProxy(self)
        self._proxy.setSourceModel(self._model)
        self._type_cache: dict[tuple[int, str], str] = {}
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(150)
        self._filter_timer.timeout.connect(self._apply_filter_now)
        self._pending_filter = ""
        self._build_timer = QTimer(self)
        self._build_timer.setInterval(0)
        self._build_timer.timeout.connect(self._process_build_queue)
        self._build_queue: deque[tuple[QStandardItem, VFSNode, VFS]] = deque()
        self._build_batch = 200
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter files…")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter)

        self._tree = QTreeView()
        self._tree.setModel(self._proxy)
        self._tree.setAnimated(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSortingEnabled(False)
        self._tree.setColumnWidth(0, 160)
        self._tree.setColumnWidth(1, 65)
        self._tree.setColumnWidth(2, 60)
        self._tree.setColumnWidth(3, 90)
        self._tree.doubleClicked.connect(self._on_double_click)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.selectionModel().selectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._tree)

    def load_vfs(self, vfs: VFS) -> None:
        """Append a new VFS source to the tree."""
        self._vfs = vfs
        self._build_timer.stop()
        self._build_queue.clear()
        self._type_cache.clear()

        # Recreate model to avoid slow row-by-row clears on large trees.
        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels(["Name", "Size", "Files", "Total Size", "Type"])
        self._proxy.setSourceModel(self._model)

        root_node = vfs.root()
        row = self._node_to_row_shallow(root_node, vfs)
        self._model.appendRow(row)
        self._tree.expand(self._proxy.mapFromSource(self._model.indexFromItem(row[0])))
        if root_node.children:
            self._build_queue.append((row[0], root_node, vfs))
            self._build_timer.start()
        else:
            self.load_finished.emit()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _node_to_row_shallow(self, node: VFSNode, vfs: VFS) -> list[QStandardItem]:
        name_item = QStandardItem(node.name)
        name_item.setData(node, _ROLE_NODE)
        name_item.setData(vfs, _ROLE_VFS)
        name_item.setEditable(False)

        size_item = QStandardItem(_format_size(node.size) if not node.is_dir else "")
        size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        size_item.setEditable(False)

        files_item = QStandardItem(
            f"{vfs.file_count(node):,}" if node.is_dir else ""
        )
        files_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        files_item.setEditable(False)

        total_item = QStandardItem(
            _format_size(vfs.total_size(node)) if node.is_dir else _format_size(node.size)
        )
        total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        total_item.setEditable(False)

        type_label = self._detect_type_label(node, vfs)
        type_item = QStandardItem(type_label)
        type_item.setEditable(False)

        return [name_item, size_item, files_item, total_item, type_item]

    def _on_double_click(self, index: QModelIndex) -> None:
        proxy_index = index.siblingAtColumn(0)
        source_index = self._proxy.mapToSource(proxy_index)
        item = self._model.itemFromIndex(source_index)
        if item is None:
            return
        node: VFSNode | None = item.data(_ROLE_NODE)
        vfs: VFS | None = item.data(_ROLE_VFS)
        if node and vfs and not node.is_dir:
            self.node_activated.emit(node, vfs)

    def _on_selection_changed(self, *_: object) -> None:
        selection = self._tree.selectionModel().selectedIndexes()
        if not selection:
            return
        index = next((i for i in selection if i.column() == 0), selection[0])
        proxy_index = index.siblingAtColumn(0)
        source_index = self._proxy.mapToSource(proxy_index)
        item = self._model.itemFromIndex(source_index)
        if item is None:
            return
        node: VFSNode | None = item.data(_ROLE_NODE)
        vfs: VFS | None = item.data(_ROLE_VFS)
        if node and vfs:
            self.node_selected.emit(node, vfs)

    def _on_context_menu(self, pos: object) -> None:
        index = self._tree.indexAt(pos)
        if not index.isValid():
            return
        proxy_index = index.siblingAtColumn(0)
        source_index = self._proxy.mapToSource(proxy_index)
        item = self._model.itemFromIndex(source_index)
        if item is None:
            return
        node: VFSNode | None = item.data(_ROLE_NODE)
        vfs: VFS | None = item.data(_ROLE_VFS)
        if not node or not vfs:
            return
        menu = QMenu(self)
        open_action = menu.addAction("Open")
        open_hex_action = menu.addAction("Open in Hex")
        menu.addSeparator()
        export_action = menu.addAction("Export…")
        action = menu.exec(self._tree.viewport().mapToGlobal(pos))
        if action == open_action:
            self.open_requested.emit(node, vfs, "default")
        elif action == open_hex_action:
            self.open_requested.emit(node, vfs, "hex")
        elif action == export_action:
            self.export_requested.emit(node, vfs)

    def _apply_filter(self, text: str) -> None:
        self._pending_filter = text
        self._filter_timer.start()

    def _apply_filter_now(self) -> None:
        self._proxy.setFilterFixedString(self._pending_filter)

    def _process_build_queue(self) -> None:
        if not self._build_queue:
            self._build_timer.stop()
            self.load_finished.emit()
            return

        processed = 0
        while self._build_queue and processed < self._build_batch:
            parent_item, node, vfs = self._build_queue.popleft()
            for child in node.children:
                row = self._node_to_row_shallow(child, vfs)
                parent_item.appendRow(row)
                if child.is_dir and child.children:
                    self._build_queue.append((row[0], child, vfs))
            processed += 1

        if not self._build_queue:
            self._build_timer.stop()
            self.load_finished.emit()

    def _detect_type_label(self, node: VFSNode, vfs: VFS) -> str:
        if node.is_dir:
            return "DIR"
        cache_key = (id(vfs), node.path)
        if cache_key in self._type_cache:
            return self._type_cache[cache_key]
        label = ""
        try:
            peek = vfs.peek(node, 16)
            if peek.startswith(_SQLITE_MAGIC):
                label = "SQLite"
            elif peek.startswith(_BPLIST_MAGIC):
                label = "bplist"
            elif peek.startswith(_XML_PLIST_SIG):
                label = "plist"
            else:
                label = self._label_from_registry(node, vfs)
        except Exception:
            label = ""
        self._type_cache[cache_key] = label
        return label

    def _label_from_registry(self, node: VFSNode, vfs: VFS) -> str:
        try:
            import crush.parsers  # noqa: F401
            from crush.core.registry import ParserRegistry
            parser = ParserRegistry.best(node, vfs)
            if parser is None:
                return ""
            return parser.DISPLAY_NAME
        except Exception:
            return ""


class _VfsFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(0)
        self.setRecursiveFilteringEnabled(True)
