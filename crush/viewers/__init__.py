# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Register built-in viewers."""
from __future__ import annotations

from crush.core.viewer_registry import ViewerRegistry


def _register_builtin_viewers() -> None:
    from crush.viewers.table_viewer import TableViewer
    from crush.viewers.tree_viewer import TreeViewer
    from crush.viewers.hex_viewer import HexViewer
    from crush.viewers.text_viewer import TextView
    from crush.viewers.image_viewer import ImageViewer
    from crush.viewers.abx_viewer import AbxViewer
    from crush.viewers.protobuf_viewer import ProtobufViewer

    ViewerRegistry.register("table", lambda r, n, v, p: TableViewer(r.data, p))
    ViewerRegistry.register("tree", lambda r, n, v, p: TreeViewer(r.data, p))
    ViewerRegistry.register("hex", lambda r, n, v, p: HexViewer(r.data, p))
    ViewerRegistry.register("text", lambda r, n, v, p: TextView(r.data, p))
    ViewerRegistry.register("image", lambda r, n, v, p: ImageViewer(r.data, p))
    ViewerRegistry.register("abx", lambda r, n, v, p: AbxViewer(r.data, p))
    ViewerRegistry.register("protobuf", lambda r, n, v, p: ProtobufViewer(r.data, p))

    from crush.viewers.log_viewer import LogViewer
    ViewerRegistry.register("log", lambda r, n, v, p: LogViewer(r.data, p))

    try:
        from crush.viewers.media_viewer import MediaViewer
        ViewerRegistry.register("media", lambda r, n, v, p: MediaViewer(r.data, p))
    except ImportError:
        pass


_register_builtin_viewers()
