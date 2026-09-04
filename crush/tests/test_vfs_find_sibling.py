# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Tests for find_sibling()/_find_node_by_path() (crush/core/vfs.py).

Regression coverage for switching _find_node_by_path from an unconditional
full-tree recursion (touches every node) to descending by path segment (only
touches nodes on the direct path from root to the target) — a real
performance bug on large VFS trees (full filesystem extractions can have
hundreds of thousands of nodes) found while investigating MMKV .crc lookup
lag, but the function is shared with SQLite's -wal/-shm discovery too.
"""
from __future__ import annotations

from crush.core.vfs import VFSNode, find_sibling


class _FakeVFS:
    def __init__(self, root_node: VFSNode) -> None:
        self._root = root_node

    def root(self) -> VFSNode:
        return self._root


def _dir(name: str, path: str, children: list[VFSNode] | None = None) -> VFSNode:
    return VFSNode(name=name, path=path, is_dir=True, children=children or [])


def _file(name: str, path: str) -> VFSNode:
    return VFSNode(name=name, path=path, is_dir=False, size=1)


def test_finds_sibling_in_same_directory() -> None:
    target = _file("mmkv.default", "/data/mmkv/mmkv.default")
    sibling = _file("mmkv.default.crc", "/data/mmkv/mmkv.default.crc")
    root = _dir("/", "/", [_dir("data", "/data", [_dir("mmkv", "/data/mmkv", [target, sibling])])])
    vfs = _FakeVFS(root)

    result = find_sibling(target, vfs, ".crc")
    assert result is sibling


def test_returns_none_when_sibling_does_not_exist() -> None:
    target = _file("mmkv.default", "/data/mmkv/mmkv.default")
    root = _dir("/", "/", [_dir("data", "/data", [_dir("mmkv", "/data/mmkv", [target])])])
    vfs = _FakeVFS(root)

    assert find_sibling(target, vfs, ".crc") is None


def test_does_not_match_a_same_named_file_in_a_different_directory() -> None:
    """A file with the same name elsewhere in the tree must never be mistaken
    for the sibling — only the exact same directory counts."""
    target = _file("mmkv.default", "/data/appA/mmkv.default")
    decoy = _file("mmkv.default.crc", "/data/appB/mmkv.default.crc")
    root = _dir("/", "/", [_dir("data", "/data", [
        _dir("appA", "/data/appA", [target]),
        _dir("appB", "/data/appB", [decoy]),
    ])])
    vfs = _FakeVFS(root)

    assert find_sibling(target, vfs, ".crc") is None


def test_root_level_file() -> None:
    target = _file("a.db", "/a.db")
    sibling = _file("a.db-wal", "/a.db-wal")
    root = _dir("/", "/", [target, sibling])
    vfs = _FakeVFS(root)

    assert find_sibling(target, vfs, "-wal") is sibling


def test_finds_sibling_in_large_tree_without_full_traversal() -> None:
    """Build a wide/deep tree and confirm the lookup still works correctly
    (the actual performance win — only touching nodes on the direct path,
    not all of them — is what the rewrite is for; this checks correctness
    holds at scale, not a timing assertion, which would be flaky in CI)."""
    # Many sibling directories at the same level as the target's parent.
    decoys = [_dir(f"other{i}", f"/data/other{i}", [_file("x", f"/data/other{i}/x")]) for i in range(5000)]
    target = _file("store", "/data/mmkv/store")
    sibling = _file("store.crc", "/data/mmkv/store.crc")
    mmkv_dir = _dir("mmkv", "/data/mmkv", [target, sibling])
    root = _dir("/", "/", [_dir("data", "/data", [*decoys, mmkv_dir])])
    vfs = _FakeVFS(root)

    assert find_sibling(target, vfs, ".crc") is sibling
