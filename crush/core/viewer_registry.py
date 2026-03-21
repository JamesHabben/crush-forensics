# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Viewer registry for mapping viewer types to QWidget factories."""
from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QWidget

from crush.core.vfs import VFS, VFSNode
from crush.parsers.base import ParseResult

ViewerFactory = Callable[[ParseResult, VFSNode, VFS, QWidget], QWidget]


class ViewerRegistry:
    _factories: dict[str, ViewerFactory] = {}

    @classmethod
    def register(cls, viewer_type: str, factory: ViewerFactory) -> None:
        cls._factories[viewer_type] = factory

    @classmethod
    def get(cls, viewer_type: str) -> ViewerFactory | None:
        return cls._factories.get(viewer_type)
