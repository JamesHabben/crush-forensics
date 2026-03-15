# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Viewer factory — maps ParseResult.viewer_type to the right QWidget."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import ParseResult


def make_viewer(result: ParseResult, node: VFSNode, vfs: VFS, parent: QWidget) -> QWidget:
    """Return the appropriate viewer widget for the given ParseResult."""
    vtype = result.viewer_type

    if vtype == "table":
        from crush.viewers.table_viewer import TableViewer
        return TableViewer(result.data, parent)

    if vtype == "tree":
        from crush.viewers.tree_viewer import TreeViewer
        return TreeViewer(result.data, parent)

    if vtype == "hex":
        from crush.viewers.hex_viewer import HexViewer
        return HexViewer(result.data, parent)

    if vtype == "text":
        from crush.viewers.text_viewer import TextView
        return TextView(result.data, parent)

    if vtype == "image":
        from crush.viewers.image_viewer import ImageViewer
        return ImageViewer(result.data, parent)

    if vtype == "media":
        from crush.viewers.media_viewer import MediaViewer
        return MediaViewer(result.data, parent)

    if vtype == "abx":
        from crush.viewers.abx_viewer import AbxViewer
        return AbxViewer(result.data, parent)

    # Unknown type — show a placeholder
    placeholder = QLabel(f"No viewer available for type: {vtype!r}")
    return placeholder
