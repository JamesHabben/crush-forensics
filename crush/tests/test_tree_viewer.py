# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Tests for TreeViewer (crush/viewers/tree_viewer.py)."""
from __future__ import annotations

from crush.viewers.tree_viewer import TreeViewer

_UINT64_MAX = (1 << 64) - 1


def _select_only_row(widget: TreeViewer) -> None:
    index = widget._model.index(0, 0)
    widget._tree.setCurrentIndex(index)


def test_scalar_uint64_max_does_not_crash_and_roundtrips(qapp) -> None:
    """A bare int in the uint64 range (e.g. an NSKeyedArchiver UID) must not
    make Qt's QVariant conversion raise OverflowError while building the
    tree, and must still be retrievable afterwards."""
    widget = TreeViewer({"uid": _UINT64_MAX})
    _select_only_row(widget)
    obj, key = widget._current_obj_and_key()
    assert key == "uid"
    assert obj == _UINT64_MAX


def test_dict_containing_uint64_max_does_not_crash_and_roundtrips(qapp) -> None:
    widget = TreeViewer({"outer": {"value": _UINT64_MAX}})
    _select_only_row(widget)
    obj, key = widget._current_obj_and_key()
    assert key == "outer"
    assert obj == {"value": _UINT64_MAX}


def test_list_containing_uint64_max_does_not_crash_and_roundtrips(qapp) -> None:
    widget = TreeViewer({"items": [_UINT64_MAX]})
    _select_only_row(widget)
    obj, key = widget._current_obj_and_key()
    assert key == "items"
    assert obj == [_UINT64_MAX]
