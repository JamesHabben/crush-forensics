"""Virtual Filesystem (VFS) abstraction.

All source types (ZIP archive, directory, future: AFF4, tar) are presented
through a single interface so viewers never need to know the origin.
"""
from __future__ import annotations

import tarfile
import threading
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import IO


@dataclass
class VFSNode:
    """A single node in the virtual filesystem tree."""
    name: str
    path: str          # Full virtual path e.g. "/var/mobile/Library/SMS/sms.db"
    is_dir: bool
    size: int = 0
    modified: float = 0.0
    accessed: float = 0.0
    changed: float = 0.0
    birth: float = 0.0
    children: list[VFSNode] = field(default_factory=list)

    @property
    def extension(self) -> str:
        return Path(self.name).suffix.lower()


class VFS(ABC):
    """Abstract virtual filesystem."""

    @abstractmethod
    def root(self) -> VFSNode: ...

    @abstractmethod
    def read(self, node: VFSNode) -> bytes: ...

    @abstractmethod
    def open(self, node: VFSNode) -> IO[bytes]: ...

    def close(self) -> None:
        """Optional cleanup for VFS implementations."""
        return None

    @abstractmethod
    def file_count(self, node: VFSNode) -> int:
        """Return number of files under node (including the node if it's a file)."""
        ...

    @abstractmethod
    def total_size(self, node: VFSNode) -> int:
        """Return total size of files under node (including the node if it's a file)."""
        ...

    def peek(self, node: VFSNode, n: int = 32) -> bytes:
        """Return first n bytes for magic-byte sniffing."""
        with self.open(node) as src:
            return src.read(n)


class DirectoryVFS(VFS):
    """VFS backed by a plain directory on disk."""

    def __init__(self, path: str | Path) -> None:
        self._root_path = Path(path)
        self._tree = self._build_node(self._root_path)
        self._file_counts: dict[str, int] = {}
        self._total_sizes: dict[str, int] = {}
        self._compute_file_counts(self._tree)
        self._compute_total_sizes(self._tree)

    def root(self) -> VFSNode:
        return self._tree

    def _build_node(self, path: Path) -> VFSNode:
        stat = path.stat()
        node = VFSNode(
            name=path.name or str(path),
            path=str(path),
            is_dir=path.is_dir(),
            size=stat.st_size if path.is_file() else 0,
            modified=stat.st_mtime,
            accessed=stat.st_atime,
            changed=stat.st_ctime,
            birth=getattr(stat, "st_birthtime", 0.0),
        )
        if path.is_dir():
            node.children = sorted(
                [self._build_node(child) for child in path.iterdir()],
                key=lambda n: (not n.is_dir, n.name.lower()),
            )
        return node

    def read(self, node: VFSNode) -> bytes:
        return Path(node.path).read_bytes()

    def open(self, node: VFSNode) -> IO[bytes]:
        return open(node.path, "rb")

    def file_count(self, node: VFSNode) -> int:
        return self._file_counts.get(node.path, 0)

    def total_size(self, node: VFSNode) -> int:
        return self._total_sizes.get(node.path, 0)

    def _compute_file_counts(self, node: VFSNode) -> int:
        if not node.is_dir:
            self._file_counts[node.path] = 1
            return 1
        total = 0
        for child in node.children:
            total += self._compute_file_counts(child)
        self._file_counts[node.path] = total
        return total

    def _compute_total_sizes(self, node: VFSNode) -> int:
        if not node.is_dir:
            self._total_sizes[node.path] = node.size
            return node.size
        total = 0
        for child in node.children:
            total += self._compute_total_sizes(child)
        self._total_sizes[node.path] = total
        return total


class ZipVFS(VFS):
    """VFS backed by a ZIP archive (iOS/Android full-fs extractions).

    A single ZipFile handle is shared across threads and protected by
    _zf_lock.  open() returns a BytesIO so callers never hold the lock
    while processing file content.
    """

    def __init__(self, path: str | Path) -> None:
        self._zip_path = Path(path)
        self._zf = zipfile.ZipFile(self._zip_path, "r")
        self._zf_lock = threading.Lock()
        self._zip_names: dict[str, str] = {}
        self._tree = self._build_tree()
        self._file_counts: dict[str, int] = {}
        self._total_sizes: dict[str, int] = {}
        self._compute_file_counts(self._tree)
        self._compute_total_sizes(self._tree)

    def _build_tree(self) -> VFSNode:
        root = VFSNode(name=self._zip_path.name, path="/", is_dir=True)
        nodes: dict[str, VFSNode] = {"/": root}

        for info in sorted(self._zf.infolist(), key=lambda i: i.filename):
            parts = info.filename.rstrip("/").split("/")
            for depth, _ in enumerate(parts, 1):
                virtual_path = "/" + "/".join(parts[:depth])
                if virtual_path not in nodes:
                    is_dir = depth < len(parts) or info.filename.endswith("/")
                    zip_ts = 0.0
                    if info.date_time:
                        from datetime import datetime
                        zip_ts = datetime(*info.date_time).timestamp()
                    node = VFSNode(
                        name=parts[depth - 1],
                        path=virtual_path,
                        is_dir=is_dir,
                        size=info.file_size if not is_dir else 0,
                        modified=zip_ts,
                    )
                    parent_path = "/" + "/".join(parts[: depth - 1]) if depth > 1 else "/"
                    nodes[parent_path].children.append(node)
                    nodes[virtual_path] = node
                if depth == len(parts) and not info.filename.endswith("/"):
                    self._zip_names[virtual_path] = info.filename

        for node in nodes.values():
            node.children.sort(key=lambda n: (not n.is_dir, n.name.lower()))
        return root

    def root(self) -> VFSNode:
        return self._tree

    def peek(self, node: VFSNode, n: int = 32) -> bytes:
        with self._zf_lock:
            with self._zf.open(self._zip_name(node)) as f:
                return f.read(n)

    def read(self, node: VFSNode) -> bytes:
        with self._zf_lock:
            return self._zf.read(self._zip_name(node))

    def open(self, node: VFSNode) -> IO[bytes]:
        return BytesIO(self.read(node))

    def _zip_name(self, node: VFSNode) -> str:
        return self._zip_names.get(node.path, node.path.lstrip("/"))

    def close(self) -> None:
        self._zf.close()

    def file_count(self, node: VFSNode) -> int:
        return self._file_counts.get(node.path, 0)

    def total_size(self, node: VFSNode) -> int:
        return self._total_sizes.get(node.path, 0)

    def _compute_file_counts(self, node: VFSNode) -> int:
        if not node.is_dir:
            self._file_counts[node.path] = 1
            return 1
        total = 0
        for child in node.children:
            total += self._compute_file_counts(child)
        self._file_counts[node.path] = total
        return total

    def _compute_total_sizes(self, node: VFSNode) -> int:
        if not node.is_dir:
            self._total_sizes[node.path] = node.size
            return node.size
        total = 0
        for child in node.children:
            total += self._compute_total_sizes(child)
        self._total_sizes[node.path] = total
        return total


class TarVFS(VFS):
    """VFS backed by a TAR archive (plain, gzip, bzip2, or xz compressed).

    Compressed tar files cannot seek randomly, so reads are serialized with a
    per-instance lock to allow safe concurrent peek() from multiple threads.
    """

    def __init__(self, path: str | Path) -> None:
        self._tar_path = Path(path)
        self._tf = tarfile.open(str(self._tar_path), "r:*")
        self._tf_lock = threading.Lock()
        self._members: dict[str, tarfile.TarInfo] = {}
        self._tree = self._build_tree()
        self._file_counts: dict[str, int] = {}
        self._total_sizes: dict[str, int] = {}
        self._compute_file_counts(self._tree)
        self._compute_total_sizes(self._tree)

    def _build_tree(self) -> VFSNode:
        root = VFSNode(name=self._tar_path.name, path="/", is_dir=True)
        nodes: dict[str, VFSNode] = {"/": root}

        for member in self._tf.getmembers():
            raw_name = member.name.lstrip("./")
            if not raw_name:
                continue
            parts = raw_name.split("/")
            for depth in range(1, len(parts) + 1):
                virtual_path = "/" + "/".join(parts[:depth])
                if virtual_path in nodes:
                    continue
                is_dir = depth < len(parts) or member.isdir()
                node = VFSNode(
                    name=parts[depth - 1],
                    path=virtual_path,
                    is_dir=is_dir,
                    size=member.size if (not is_dir and member.isfile()) else 0,
                    modified=float(member.mtime),
                )
                parent_path = "/" + "/".join(parts[: depth - 1]) if depth > 1 else "/"
                if parent_path in nodes:
                    nodes[parent_path].children.append(node)
                nodes[virtual_path] = node
            if member.isfile():
                self._members[virtual_path] = member

        for node in nodes.values():
            node.children.sort(key=lambda n: (not n.is_dir, n.name.lower()))
        return root

    def root(self) -> VFSNode:
        return self._tree

    def read(self, node: VFSNode) -> bytes:
        member = self._members.get(node.path)
        if member is None:
            raise FileNotFoundError(f"Not in TAR: {node.path}")
        with self._tf_lock:
            f = self._tf.extractfile(member)
            if f is None:
                raise OSError(f"Cannot extract (symlink or special file): {node.path}")
            return f.read()

    def open(self, node: VFSNode) -> IO[bytes]:
        return BytesIO(self.read(node))

    def close(self) -> None:
        self._tf.close()

    def file_count(self, node: VFSNode) -> int:
        return self._file_counts.get(node.path, 0)

    def total_size(self, node: VFSNode) -> int:
        return self._total_sizes.get(node.path, 0)

    def _compute_file_counts(self, node: VFSNode) -> int:
        if not node.is_dir:
            self._file_counts[node.path] = 1
            return 1
        total = 0
        for child in node.children:
            total += self._compute_file_counts(child)
        self._file_counts[node.path] = total
        return total

    def _compute_total_sizes(self, node: VFSNode) -> int:
        if not node.is_dir:
            self._total_sizes[node.path] = node.size
            return node.size
        total = 0
        for child in node.children:
            total += self._compute_total_sizes(child)
        self._total_sizes[node.path] = total
        return total


class BytesVFS(VFS):
    """VFS backed by a single in-memory bytes object (for artifact chaining)."""

    def __init__(self, data: bytes, name: str = "blob") -> None:
        self._data = data
        self._root = VFSNode(
            name=name,
            path=f"/{name}",
            is_dir=False,
            size=len(data),
        )

    def root(self) -> VFSNode:
        return self._root

    def read(self, node: VFSNode) -> bytes:
        return self._data

    def open(self, node: VFSNode) -> IO[bytes]:
        return BytesIO(self._data)

    def file_count(self, node: VFSNode) -> int:
        return 1

    def total_size(self, node: VFSNode) -> int:
        return len(self._data)


def find_sibling(node: VFSNode, vfs: VFS, name_suffix: str) -> "VFSNode | None":
    """Find a sibling VFSNode whose name equals node.name + name_suffix."""
    target_name = node.name + name_suffix
    parent_path = node.path.rsplit("/", 1)[0] or "/"
    target_path = (parent_path.rstrip("/") + "/" + target_name).replace("//", "/")
    return _find_node_by_path(vfs.root(), target_path)


def _find_node_by_path(node: VFSNode, path: str) -> "VFSNode | None":
    if node.path == path:
        return node
    for child in node.children:
        result = _find_node_by_path(child, path)
        if result is not None:
            return result
    return None


def open_vfs(path: str | Path) -> VFS:
    """Factory — open the right VFS type based on the source path."""
    p = Path(path)
    if p.is_dir():
        return DirectoryVFS(p)
    name_lower = p.name.lower()
    if p.suffix.lower() == ".zip":
        return ZipVFS(p)
    if (
        p.suffix.lower() in (".tar", ".tgz", ".tbz2", ".txz")
        or name_lower.endswith(".tar.gz")
        or name_lower.endswith(".tar.bz2")
        or name_lower.endswith(".tar.xz")
    ):
        return TarVFS(p)
    if p.is_file():
        return FileVFS(p)
    raise ValueError(f"Unsupported source type: {p}")


class FileVFS(VFS):
    """VFS backed by a single file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        stat = self._path.stat()
        self._root = VFSNode(
            name=self._path.name,
            path=str(self._path),
            is_dir=False,
            size=stat.st_size,
            modified=stat.st_mtime,
            accessed=stat.st_atime,
            changed=stat.st_ctime,
            birth=getattr(stat, "st_birthtime", 0.0),
        )

    def root(self) -> VFSNode:
        return self._root

    def read(self, node: VFSNode) -> bytes:
        return Path(node.path).read_bytes()

    def open(self, node: VFSNode) -> IO[bytes]:
        return open(node.path, "rb")

    def file_count(self, node: VFSNode) -> int:
        return 1

    def total_size(self, node: VFSNode) -> int:
        return node.size
