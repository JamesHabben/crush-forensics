"""Parser registry."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crush.parsers.base import AbstractParser
    from crush.core.vfs import VFS, VFSNode


class ParserRegistry:
    _parsers: list["AbstractParser"] = []

    @classmethod
    def register(cls, parser: "AbstractParser") -> None:
        cls._parsers.append(parser)

    @classmethod
    def candidates(cls, node: "VFSNode", vfs: "VFS") -> list["AbstractParser"]:
        if node.is_dir:
            return []
        peek = vfs.peek(node)
        return [p for p in cls._parsers if p.can_parse(node.path, peek)]

    @classmethod
    def best(cls, node: "VFSNode", vfs: "VFS") -> "AbstractParser | None":
        candidates = cls.candidates(node, vfs)
        return candidates[0] if candidates else None
