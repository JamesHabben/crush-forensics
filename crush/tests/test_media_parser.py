# SPDX-License-Identifier: Apache-2.0
"""Tests for MediaParser."""
from __future__ import annotations

from pathlib import Path

import pytest

from crush.core.vfs import DirectoryVFS
from crush.parsers.media_parser import MediaParser

_OGG_STUB = b"OggS" + b"\x00" * 60
_AMR_NB_STUB = b"#!AMR\n" + b"\x00" * 60
_AMR_WB_STUB = b"#!AMR-WB\n" + b"\x00" * 60

_AUDIO_EXTENSIONS = [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".amr"]
_VIDEO_EXTENSIONS = [".mp4", ".m4v", ".mov", ".mkv", ".avi", ".webm", ".3gp", ".3g2"]


def _make_node(tmp_path: Path, name: str, data: bytes):
    (tmp_path / name).write_bytes(data)
    vfs = DirectoryVFS(tmp_path)
    return next(c for c in vfs.root().children if c.name == name), vfs


# ---------------------------------------------------------------------------
# can_parse — extension matching
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ext", _AUDIO_EXTENSIONS)
def test_can_parse_audio_by_extension(tmp_path: Path, ext: str) -> None:
    name = f"test{ext}"
    (tmp_path / name).write_bytes(b"\x00" * 32)
    vfs = DirectoryVFS(tmp_path)
    node = next(c for c in vfs.root().children if c.name == name)
    assert MediaParser().can_parse(node.path, vfs.peek(node))


@pytest.mark.parametrize("ext", _VIDEO_EXTENSIONS)
def test_can_parse_video_by_extension(tmp_path: Path, ext: str) -> None:
    name = f"test{ext}"
    (tmp_path / name).write_bytes(b"\x00" * 32)
    vfs = DirectoryVFS(tmp_path)
    node = next(c for c in vfs.root().children if c.name == name)
    assert MediaParser().can_parse(node.path, vfs.peek(node))


# ---------------------------------------------------------------------------
# can_parse — magic byte fallback (renamed / extensionless files)
# ---------------------------------------------------------------------------

def test_can_parse_ogg_magic_renamed_to_bin(tmp_path: Path) -> None:
    node, vfs = _make_node(tmp_path, "voice_note.bin", _OGG_STUB)
    assert MediaParser().can_parse(node.path, vfs.peek(node))


def test_can_parse_amr_nb_magic_renamed_to_bin(tmp_path: Path) -> None:
    node, vfs = _make_node(tmp_path, "recording.bin", _AMR_NB_STUB)
    assert MediaParser().can_parse(node.path, vfs.peek(node))


def test_can_parse_amr_wb_magic_renamed_to_bin(tmp_path: Path) -> None:
    node, vfs = _make_node(tmp_path, "recording.bin", _AMR_WB_STUB)
    assert MediaParser().can_parse(node.path, vfs.peek(node))


def test_cannot_parse_unknown_extension_no_magic(tmp_path: Path) -> None:
    node, vfs = _make_node(tmp_path, "data.xyz", b"\x00" * 32)
    assert not MediaParser().can_parse(node.path, vfs.peek(node))


# ---------------------------------------------------------------------------
# parse — viewer type and raw data integrity
# ---------------------------------------------------------------------------

def test_parse_viewer_type_is_media(tmp_path: Path) -> None:
    node, vfs = _make_node(tmp_path, "test.mp3", b"\xff\xfb" + b"\x00" * 100)
    result = MediaParser().parse(node, vfs)
    assert result.viewer_type == "media"


def test_parse_preserves_raw_data(tmp_path: Path) -> None:
    payload = b"\xff\xfb" + b"\xAA\xBB\xCC\xDD" * 25
    node, vfs = _make_node(tmp_path, "test.mp3", payload)
    result = MediaParser().parse(node, vfs)
    assert result.data == payload


def test_parse_metadata_contains_file_size(tmp_path: Path) -> None:
    node, vfs = _make_node(tmp_path, "test.mp4", b"\x00\x00\x00\x20ftyp" + b"\x00" * 100)
    result = MediaParser().parse(node, vfs)
    assert "File size" in result.metadata


@pytest.mark.parametrize("ext,data", [
    (".mp3", b"\xff\xfb" + b"\x00" * 32),
    (".wav", b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 32),
    (".flac", b"fLaC" + b"\x00" * 32),
    (".mp4", b"\x00\x00\x00\x20ftyp" + b"\x00" * 32),
    (".mkv", b"\x1a\x45\xdf\xa3" + b"\x00" * 32),
    (".avi", b"RIFF\x00\x00\x00\x00AVI " + b"\x00" * 32),
])
def test_parse_various_formats_return_media_viewer(tmp_path: Path, ext: str, data: bytes) -> None:
    node, vfs = _make_node(tmp_path, f"test{ext}", data)
    result = MediaParser().parse(node, vfs)
    assert result.viewer_type == "media"
    assert result.data == data


# ---------------------------------------------------------------------------
# parse — OGG/AMR metadata extraction (PyAV path)
# ---------------------------------------------------------------------------

def test_parse_ogg_stub_does_not_crash(tmp_path: Path) -> None:
    node, vfs = _make_node(tmp_path, "voice.ogg", _OGG_STUB)
    result = MediaParser().parse(node, vfs)
    assert result.viewer_type == "media"
    assert isinstance(result.metadata, dict)
    assert "File size" in result.metadata


def test_parse_amr_stub_does_not_crash(tmp_path: Path) -> None:
    node, vfs = _make_node(tmp_path, "recording.amr", _AMR_NB_STUB)
    result = MediaParser().parse(node, vfs)
    assert result.viewer_type == "media"
    assert isinstance(result.metadata, dict)
