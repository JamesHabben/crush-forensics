# SPDX-License-Identifier: Apache-2.0
"""Forensic-quality tests: evidence integrity, read-only enforcement, reproducibility.

A forensic tool has stricter requirements than ordinary software:
  - It must never modify the evidence it reads.
  - It must produce identical results for identical inputs (reproducibility).
  - It must work correctly when evidence is on read-only media.
  - Known reference inputs must always yield known reference outputs.

These tests complement the functional parser tests.  Where functional tests ask
"does it parse?", these tests ask "is it safe to run on real evidence?".
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

import pytest

from crush.core.vfs import DirectoryVFS, TarVFS, VFSNode, ZipVFS
from crush.parsers.plist_parser import PlistParser
from crush.parsers.realm_parser import RealmParser
from crush.parsers.sqlite_parser import SQLiteParser
from crush.tests.conftest import FIXTURES_DIR


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_nodes(node: VFSNode) -> list[VFSNode]:
    """Flatten a VFSNode tree, returning only non-directory nodes."""
    if not node.is_dir:
        return [node]
    result: list[VFSNode] = []
    for child in node.children:
        result.extend(_file_nodes(child))
    return result


# ---------------------------------------------------------------------------
# 1. Source immutability — VFS reads must never alter what they read
# ---------------------------------------------------------------------------

@pytest.mark.forensic(
    category="Source Immutability",
    desc="DirectoryVFS read/peek must leave source file bytes unchanged",
)
def test_directory_vfs_does_not_modify_source(tmp_path: Path) -> None:
    content = b"SQLite format 3\x00" + b"\x00" * 100
    src = tmp_path / "evidence.db"
    src.write_bytes(content)
    digest_before = _sha256_file(src)

    vfs = DirectoryVFS(tmp_path)
    root = vfs.root()
    node = next(c for c in root.children if c.name == "evidence.db")
    _ = vfs.read(node)
    _ = vfs.peek(node)

    assert _sha256_file(src) == digest_before, "DirectoryVFS modified the source file"


@pytest.mark.forensic(
    category="Source Immutability",
    desc="Exhaustively reading every entry of a ZIP archive must leave it byte-identical",
)
def test_zip_vfs_does_not_modify_archive(zip_fixture: Path) -> None:
    digest_before = _sha256_file(zip_fixture)

    vfs = ZipVFS(zip_fixture)
    for node in vfs.storage_ordered_files():
        _ = vfs.read(node)
    vfs.close()

    assert _sha256_file(zip_fixture) == digest_before, "ZipVFS modified the source archive"


@pytest.mark.forensic(
    category="Source Immutability",
    desc="Exhaustively reading every entry of a TAR archive must leave it byte-identical",
)
def test_tar_vfs_does_not_modify_archive(tar_fixture: Path) -> None:
    digest_before = _sha256_file(tar_fixture)

    vfs = TarVFS(tar_fixture)
    for node in _file_nodes(vfs.root()):
        _ = vfs.read(node)
    vfs.close()

    assert _sha256_file(tar_fixture) == digest_before, "TarVFS modified the source archive"


# ---------------------------------------------------------------------------
# 2. No side-effect files — parsers must not create siblings next to evidence
# ---------------------------------------------------------------------------

@pytest.mark.forensic(
    category="No Side Effects",
    desc="SQLiteParser must preserve the WAL companion intact — parsing must not checkpoint or truncate it",
)
def test_sqlite_parser_preserves_wal_companion(tmp_path: Path) -> None:
    db_path = tmp_path / "wal_test.sqlite"

    # Simulate an app that is running during acquisition: writer commits, then a
    # reader holds an open transaction so SQLite cannot checkpoint on writer close.
    writer = sqlite3.connect(str(db_path))
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE t (x TEXT)")
    writer.execute("INSERT INTO t VALUES ('forensic_test')")
    writer.commit()
    reader = sqlite3.connect(str(db_path))
    reader.execute("BEGIN")
    reader.execute("SELECT * FROM t").fetchall()
    writer.close()  # cannot checkpoint — reader holds a snapshot

    wal_path = tmp_path / "wal_test.sqlite-wal"
    assert wal_path.exists() and wal_path.stat().st_size > 0, \
        "Test setup failed: SQLite did not create a WAL file"
    wal_size_before = wal_path.stat().st_size

    try:
        vfs = DirectoryVFS(tmp_path)
        root = vfs.root()
        node = next(c for c in root.children if c.name == "wal_test.sqlite")
        result = SQLiteParser().parse(node, vfs)
    finally:
        reader.close()

    tmp_wal = Path(str(result.data["__db_path"]) + "-wal")
    assert tmp_wal.exists(), \
        "Parser checkpointed and deleted the WAL companion — open the DB connection read-only"
    assert tmp_wal.stat().st_size == wal_size_before, \
        "Parser checkpointed and truncated the WAL companion — open the DB connection read-only"


@pytest.mark.forensic(
    category="No Side Effects",
    desc="SQLiteParser must not create -wal, -journal, or any sibling file next to the evidence",
)
def test_sqlite_parse_creates_no_sibling_files(tmp_path: Path) -> None:
    (tmp_path / "minimal.sqlite").write_bytes(
        (FIXTURES_DIR / "minimal.sqlite").read_bytes()
    )
    files_before = set(tmp_path.iterdir())

    vfs = DirectoryVFS(tmp_path)
    root = vfs.root()
    node = next(c for c in root.children if c.name == "minimal.sqlite")
    SQLiteParser().parse(node, vfs)

    new_files = set(tmp_path.iterdir()) - files_before
    assert new_files == set(), f"Parser left unexpected files next to evidence: {new_files}"


# ---------------------------------------------------------------------------
# 3. Read-only media — tool must work when evidence is chmod 0o444 / 0o555
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.name == "nt", reason="chmod semantics differ on Windows")
@pytest.mark.forensic(
    category="Read-only Media",
    desc="SQLiteParser must succeed when the evidence directory is 0o555 and file is 0o444",
)
def test_sqlite_parser_works_on_readonly_media(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    db = evidence_dir / "minimal.sqlite"
    db.write_bytes((FIXTURES_DIR / "minimal.sqlite").read_bytes())

    db.chmod(0o444)
    evidence_dir.chmod(0o555)
    try:
        vfs = DirectoryVFS(evidence_dir)
        root = vfs.root()
        node = next(c for c in root.children if c.name == "minimal.sqlite")
        result = SQLiteParser().parse(node, vfs)
        assert result.viewer_type == "table"
        assert "evidence" in result.data
    finally:
        evidence_dir.chmod(0o755)
        db.chmod(0o644)


@pytest.mark.skipif(os.name == "nt", reason="chmod semantics differ on Windows")
@pytest.mark.forensic(
    category="Read-only Media",
    desc="ZipVFS must read all entries when the archive file is chmod 0o444",
)
def test_zip_vfs_works_on_readonly_media(zip_fixture: Path) -> None:
    zip_fixture.chmod(0o444)
    try:
        vfs = ZipVFS(zip_fixture)
        for node in vfs.storage_ordered_files():
            _ = vfs.read(node)
        vfs.close()
    finally:
        zip_fixture.chmod(0o644)


@pytest.mark.skipif(os.name == "nt", reason="chmod semantics differ on Windows")
@pytest.mark.forensic(
    category="Read-only Media",
    desc="TarVFS must read all entries when the archive file is chmod 0o444",
)
def test_tar_vfs_works_on_readonly_media(tar_fixture: Path) -> None:
    tar_fixture.chmod(0o444)
    try:
        vfs = TarVFS(tar_fixture)
        for node in _file_nodes(vfs.root()):
            _ = vfs.read(node)
        vfs.close()
    finally:
        tar_fixture.chmod(0o644)


# ---------------------------------------------------------------------------
# 4. Known-output verification — committed fixtures must parse to known values
# ---------------------------------------------------------------------------

@pytest.mark.forensic(
    category="Known-output Verification",
    desc="minimal.sqlite must parse to exactly: table 'evidence', columns [id, note], row (1, 'test_entry')",
)
def test_sqlite_fixture_known_output(sqlite_fixture: Path) -> None:
    vfs = DirectoryVFS(sqlite_fixture.parent)
    root = vfs.root()
    node = next(c for c in root.children if c.name == sqlite_fixture.name)

    result = SQLiteParser().parse(node, vfs)

    assert result.viewer_type == "table"
    assert "evidence" in result.data
    tbl = result.data["evidence"]
    assert tbl["columns"] == ["id", "note"]
    assert tbl["rows"] == [[1, "test_entry"]]


@pytest.mark.forensic(
    category="Known-output Verification",
    desc="minimal_binary.plist must parse to exactly: {application, version=1, verified=True}, format=binary",
)
def test_plist_fixture_known_output(plist_fixture: Path) -> None:
    vfs = DirectoryVFS(plist_fixture.parent)
    root = vfs.root()
    node = next(c for c in root.children if c.name == plist_fixture.name)

    result = PlistParser().parse(node, vfs)

    assert result.viewer_type == "tree"
    assert result.data["application"] == "crush-forensics"
    assert result.data["version"] == 1
    assert result.data["verified"] is True
    assert result.metadata["Format"] == "binary"


@pytest.mark.forensic(
    category="Known-output Verification",
    desc="minimal.zip must contain exactly: evidence/minimal.sqlite and evidence/minimal_binary.plist",
)
def test_zip_fixture_contains_expected_entries(zip_fixture: Path) -> None:
    vfs = ZipVFS(zip_fixture)
    names = {node.name for node in vfs.storage_ordered_files()}
    assert names == {"minimal.sqlite", "minimal_binary.plist"}
    vfs.close()


@pytest.mark.forensic(
    category="Known-output Verification",
    desc="minimal.tar.gz must contain exactly: evidence/minimal.sqlite and evidence/minimal_binary.plist",
)
def test_tar_fixture_contains_expected_entries(tar_fixture: Path) -> None:
    vfs = TarVFS(tar_fixture)
    names = {node.name for node in _file_nodes(vfs.root())}
    assert names == {"minimal.sqlite", "minimal_binary.plist"}
    vfs.close()


# ---------------------------------------------------------------------------
# 5. Reproducibility — identical inputs must always yield identical outputs
# ---------------------------------------------------------------------------

@pytest.mark.forensic(
    category="Reproducibility",
    desc="Parsing the same SQLite file twice must produce structurally identical results",
)
def test_sqlite_parse_is_reproducible(sqlite_fixture: Path) -> None:
    vfs = DirectoryVFS(sqlite_fixture.parent)
    root = vfs.root()
    node = next(c for c in root.children if c.name == sqlite_fixture.name)
    parser = SQLiteParser()

    r1 = parser.parse(node, vfs)
    r2 = parser.parse(node, vfs)

    # __db_path is a temp-file path that legitimately differs between calls
    d1 = {k: v for k, v in r1.data.items() if k != "__db_path"}
    d2 = {k: v for k, v in r2.data.items() if k != "__db_path"}
    assert d1 == d2
    assert r1.metadata == r2.metadata
    assert r1.viewer_type == r2.viewer_type


@pytest.mark.forensic(
    category="Reproducibility",
    desc="Parsing the same binary plist twice must produce identical results",
)
def test_plist_parse_is_reproducible(plist_fixture: Path) -> None:
    vfs = DirectoryVFS(plist_fixture.parent)
    root = vfs.root()
    node = next(c for c in root.children if c.name == plist_fixture.name)
    parser = PlistParser()

    r1 = parser.parse(node, vfs)
    r2 = parser.parse(node, vfs)

    assert r1.data == r2.data
    assert r1.metadata == r2.metadata
    assert r1.viewer_type == r2.viewer_type


@pytest.mark.forensic(
    category="Reproducibility",
    desc="Reading the same ZIP archive entry twice must return byte-identical data",
)
def test_zip_vfs_read_is_reproducible(zip_fixture: Path) -> None:
    vfs = ZipVFS(zip_fixture)
    nodes = vfs.storage_ordered_files()
    assert nodes, "Fixture ZIP is unexpectedly empty"
    node = nodes[0]
    assert vfs.read(node) == vfs.read(node)


# ---------------------------------------------------------------------------
# Realm forensic tests
# ---------------------------------------------------------------------------

@pytest.mark.forensic(
    category="Source Immutability",
    desc="RealmParser read must leave source file bytes unchanged",
)
def test_realm_parser_does_not_modify_source(realm_fixture: Path) -> None:
    digest_before = _sha256_file(realm_fixture)

    vfs = DirectoryVFS(realm_fixture.parent)
    root = vfs.root()
    node = next(c for c in root.children if c.name == realm_fixture.name)
    _ = RealmParser().parse(node, vfs)

    assert _sha256_file(realm_fixture) == digest_before, "RealmParser modified the source file"


@pytest.mark.forensic(
    category="No Side Effects",
    desc="RealmParser must not create any sibling files next to the evidence",
)
def test_realm_parse_creates_no_sibling_files(realm_fixture: Path) -> None:
    files_before = set(realm_fixture.parent.iterdir())

    vfs = DirectoryVFS(realm_fixture.parent)
    root = vfs.root()
    node = next(c for c in root.children if c.name == realm_fixture.name)
    RealmParser().parse(node, vfs)

    new_files = set(realm_fixture.parent.iterdir()) - files_before
    assert new_files == set(), f"Parser left unexpected files next to evidence: {new_files}"


@pytest.mark.skipif(os.name == "nt", reason="chmod semantics differ on Windows")
@pytest.mark.forensic(
    category="Read-only Media",
    desc="RealmParser must succeed when evidence directory is 0o555 and file is 0o444",
)
def test_realm_parser_works_on_readonly_media(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    realm = evidence_dir / "minimal.realm"
    realm.write_bytes((FIXTURES_DIR / "minimal.realm").read_bytes())

    realm.chmod(0o444)
    evidence_dir.chmod(0o555)
    try:
        vfs = DirectoryVFS(evidence_dir)
        root = vfs.root()
        node = next(c for c in root.children if c.name == "minimal.realm")
        result = RealmParser().parse(node, vfs)
        assert result.viewer_type == "realm"
    finally:
        evidence_dir.chmod(0o755)
        realm.chmod(0o644)


@pytest.mark.forensic(
    category="Known-output Verification",
    desc="minimal.realm must parse to exactly: schema ['metadata', 'class_Evidence'], Tables found=2",
)
def test_realm_fixture_known_output(realm_fixture: Path) -> None:
    vfs = DirectoryVFS(realm_fixture.parent)
    root = vfs.root()
    node = next(c for c in root.children if c.name == realm_fixture.name)

    result = RealmParser().parse(node, vfs)

    assert result.viewer_type == "realm"
    schema = result.data["schema"]
    assert schema == ["metadata", "class_Evidence"]
    assert result.metadata["Tables found"] == "2"


@pytest.mark.forensic(
    category="Reproducibility",
    desc="Parsing the same Realm file twice must produce structurally identical results",
)
def test_realm_parse_is_reproducible(realm_fixture: Path) -> None:
    vfs = DirectoryVFS(realm_fixture.parent)
    root = vfs.root()
    node = next(c for c in root.children if c.name == realm_fixture.name)
    parser = RealmParser()

    r1 = parser.parse(node, vfs)
    r2 = parser.parse(node, vfs)

    assert r1.data == r2.data
    assert r1.metadata == r2.metadata
    assert r1.viewer_type == r2.viewer_type
    vfs.close()


# ---------------------------------------------------------------------------
# LevelDB forensic tests
# (uses the same _make_minimal_leveldb helper as test_parsers.py)
# ---------------------------------------------------------------------------

import struct as _struct


def _varint_f(n: int) -> bytes:
    out = []
    while n > 127:
        out.append((n & 0x7f) | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def _make_leveldb_fixture(path: Path) -> Path:
    """Create a minimal LevelDB directory at *path* and return it."""
    path.mkdir(parents=True, exist_ok=True)
    batch = _struct.pack("<QI", 1, 1) + b"\x01" + _varint_f(5) + b"mykey" + _varint_f(7) + b"myvalue"
    log = _struct.pack("<IHB", 0, len(batch), 1) + batch
    (path / "000001.log").write_bytes(log)
    (path / "MANIFEST-000001").write_bytes(b"")
    return path


def _sha256_dir(path: Path) -> dict[str, str]:
    """SHA-256 of every file in a directory (name → digest)."""
    return {
        f.name: hashlib.sha256(f.read_bytes()).hexdigest()
        for f in sorted(path.iterdir()) if f.is_file()
    }


@pytest.mark.forensic(
    category="Source Immutability",
    desc="LevelDB directory files must be byte-identical after parsing",
)
def test_leveldb_does_not_modify_source(tmp_path: Path) -> None:
    from crush.parsers.leveldb_parser import LeveldbParser
    db = _make_leveldb_fixture(tmp_path / "evidence.leveldb")
    digests_before = _sha256_dir(db)

    vfs = DirectoryVFS(tmp_path)
    node = next(c for c in vfs.root().children if c.name == "evidence.leveldb")
    LeveldbParser().parse(node, vfs)

    assert _sha256_dir(db) == digests_before, "LevelDB parser modified source files"


@pytest.mark.forensic(
    category="No Side Effects",
    desc="LevelDB parsing must not create files next to the evidence directory",
)
def test_leveldb_no_sibling_files(tmp_path: Path) -> None:
    from crush.parsers.leveldb_parser import LeveldbParser
    db = _make_leveldb_fixture(tmp_path / "evidence.leveldb")
    names_before = {p.name for p in tmp_path.iterdir()}

    vfs = DirectoryVFS(tmp_path)
    node = next(c for c in vfs.root().children if c.name == "evidence.leveldb")
    LeveldbParser().parse(node, vfs)

    names_after = {p.name for p in tmp_path.iterdir()}
    assert names_after == names_before, f"Side-effect files created: {names_after - names_before}"


@pytest.mark.forensic(
    category="Read-only Media",
    desc="LevelDB parser must succeed when directory and files are read-only (0o555/0o444)",
)
def test_leveldb_read_only_media(tmp_path: Path) -> None:
    from crush.parsers.leveldb_parser import LeveldbParser
    db = _make_leveldb_fixture(tmp_path / "evidence.leveldb")
    try:
        for f in db.iterdir():
            f.chmod(0o444)
        db.chmod(0o555)

        vfs = DirectoryVFS(tmp_path)
        node = next(c for c in vfs.root().children if c.name == "evidence.leveldb")
        result = LeveldbParser().parse(node, vfs)
        assert result.viewer_type == "leveldb"
    finally:
        db.chmod(0o755)
        for f in db.iterdir():
            f.chmod(0o644)


@pytest.mark.forensic(
    category="Reproducibility",
    desc="Parsing the same LevelDB directory twice must produce identical results",
)
def test_leveldb_parse_is_reproducible(tmp_path: Path) -> None:
    from crush.parsers.leveldb_parser import LeveldbParser
    db = _make_leveldb_fixture(tmp_path / "evidence.leveldb")

    vfs = DirectoryVFS(tmp_path)
    node = next(c for c in vfs.root().children if c.name == "evidence.leveldb")
    parser = LeveldbParser()

    r1 = parser.parse(node, vfs)
    r2 = parser.parse(node, vfs)

    assert r1.viewer_type == r2.viewer_type
    assert r1.metadata == r2.metadata
    assert len(r1.data["records"]) == len(r2.data["records"])
    for rec1, rec2 in zip(r1.data["records"], r2.data["records"]):
        assert rec1["state"] == rec2["state"]
        assert rec1["user_key_bytes"] == rec2["user_key_bytes"]
        assert rec1["value_bytes"] == rec2["value_bytes"]
