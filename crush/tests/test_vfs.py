# SPDX-License-Identifier: Apache-2.0
"""Tests for the VFS abstraction layer."""
from __future__ import annotations

import zipfile
from pathlib import Path

from crush.core.vfs import DirectoryVFS, ZipVFS, open_vfs


def test_directory_vfs(tmp_path: Path) -> None:
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "test.db").write_bytes(b"SQLite format 3\x00data")
    (tmp_path / "notes.txt").write_bytes(b"hello")

    vfs = DirectoryVFS(tmp_path)
    root = vfs.root()

    assert root.is_dir
    names = {child.name for child in root.children}
    assert "subdir" in names
    assert "notes.txt" in names


def test_directory_vfs_read(tmp_path: Path) -> None:
    content = b"SQLite format 3\x00"
    (tmp_path / "test.db").write_bytes(content)

    vfs = DirectoryVFS(tmp_path)
    root = vfs.root()
    file_node = next(c for c in root.children if c.name == "test.db")

    assert vfs.read(file_node) == content
    assert vfs.peek(file_node, 16) == content[:16]


def test_zip_vfs(tmp_path: Path) -> None:
    zip_path = tmp_path / "extraction.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("var/mobile/Library/SMS/sms.db", b"SQLite format 3\x00")
        zf.writestr("var/mobile/Library/Preferences/com.apple.test.plist", b"bplist00")

    vfs = ZipVFS(zip_path)
    root = vfs.root()

    assert root.is_dir
    assert root.name == "extraction.zip"


def test_open_vfs_directory(tmp_path: Path) -> None:
    vfs = open_vfs(tmp_path)
    assert isinstance(vfs, DirectoryVFS)


def test_open_vfs_zip(tmp_path: Path) -> None:
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("file.txt", b"hello")
    vfs = open_vfs(zip_path)
    assert isinstance(vfs, ZipVFS)
