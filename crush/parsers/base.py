"""Abstract parser base — all format parsers implement this interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from crush.core.vfs import VFS, VFSNode

ViewerType = Literal["table", "tree", "hex", "text", "media", "image", "abx", "log", "protobuf"]


@dataclass
class ParseResult:
    """Result returned by every parser."""
    viewer_type: ViewerType
    data: Any                          # Passed directly to the matching viewer widget
    sub_nodes: list[VFSNode] = field(default_factory=list)   # Enables cascading
    metadata: dict[str, Any] = field(default_factory=dict)   # Shown in properties panel
    text_index: str = ""               # Plaintext for the search index


class AbstractParser(ABC):
    """Base class for all Crush parsers.

    To add support for a new data type:
    1. Subclass AbstractParser in crush/parsers/your_parser.py
    2. Set SUPPORTED_EXTENSIONS, DISPLAY_NAME
    3. Implement can_parse() and parse()
    4. Register in crush/parsers/__init__.py
    """

    SUPPORTED_EXTENSIONS: list[str] = []
    SUPPORTED_MIME_TYPES: list[str] = []
    DISPLAY_NAME: str = ""

    @abstractmethod
    def can_parse(self, path: str, peek_bytes: bytes) -> bool:
        """Return True if this parser can handle the file.

        Prefer magic-byte sniffing over extension checks — extensions lie.
        peek_bytes contains the first 16 bytes of the file.
        """
        ...

    @abstractmethod
    def parse(self, node: VFSNode, vfs: VFS) -> ParseResult:
        """Parse the file and return a ParseResult."""
        ...

    def _ext_match(self, path: str) -> bool:
        """Helper: check if the file extension matches SUPPORTED_EXTENSIONS."""
        from pathlib import Path
        return Path(path).suffix.lower() in self.SUPPORTED_EXTENSIONS
