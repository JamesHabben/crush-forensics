# SPDX-License-Identifier: Apache-2.0
"""Tests for the peach-forensics binary resolver."""
from __future__ import annotations

from pathlib import Path

import pytest

from crush.core.peach_launcher import find_peach_binary


def test_find_peach_binary_override_path_used_when_set(tmp_path: Path) -> None:
    fake_binary = tmp_path / "my-peach-build"
    fake_binary.write_bytes(b"not a real binary, just needs to exist")

    resolved = find_peach_binary(override_path=str(fake_binary))

    assert resolved == fake_binary


def test_find_peach_binary_override_path_missing_raises(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    with pytest.raises(FileNotFoundError):
        find_peach_binary(override_path=str(missing))


def test_find_peach_binary_no_override_resolves_bundled_or_raises() -> None:
    # Without an override, this either finds the bundled binary for the
    # current platform (present in dev after running the download script,
    # as it is in this test environment) or raises FileNotFoundError with
    # a clear message -- either is acceptable, silent success with a wrong
    # path is not.
    try:
        resolved = find_peach_binary()
        assert resolved.exists()
    except FileNotFoundError as exc:
        assert "download_peach_binaries.py" in str(exc)
