#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Benchmark unified log conversion — single-process vs parallel.

Usage:
    # Baseline (single process)
    python scripts/benchmark_unified_log.py /path/to/diagnostics --workers 1

    # Parallel (auto-detect CPU count)
    python scripts/benchmark_unified_log.py /path/to/diagnostics

    # Parallel with explicit worker count
    python scripts/benchmark_unified_log.py /path/to/diagnostics --workers 4

Output example:
    Mode       : iOS FFS diagnostics
    Path       : /path/to/diagnostics
    Size       : 1.24 GB
    Tracev3    : 47 files in Persist/
    Workers    : 8
    Entries    : 3,842,100
    Duration   : 89.3 s
    Throughput : 43,023 entries/s
"""
from __future__ import annotations

import sys
import time
from pathlib import Path


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} TB"


def _count_tracev3(path: Path) -> int:
    persist = path / "Persist"
    if persist.is_dir():
        return len(list(persist.glob("*.tracev3")))
    return 0


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("path", help="Path to .logarchive or iOS diagnostics directory")
    ap.add_argument(
        "--workers", type=int, default=None, metavar="N",
        help="Parallel workers (default: cpu_count; use 1 for single-process baseline)",
    )
    args = ap.parse_args()

    target = Path(args.path).expanduser().resolve()
    if not target.exists():
        print(f"Error: {target} does not exist")
        sys.exit(1)

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from crush.core.vfs import DirectoryVFS
    from crush.parsers.unified_log_parser import (
        UnifiedLogConverter,
        is_ios_diagnostics_node,
    )

    is_logarchive = target.name.lower().endswith(".logarchive") or (
        target.is_dir() and (target / "Persist").is_dir()
    )

    vfs = DirectoryVFS(target.parent)

    node = None
    for child in vfs.root().children:
        if child.name == target.name:
            node = child
            break
    if node is None:
        print(f"Error: could not locate {target.name} in VFS")
        sys.exit(1)

    import os
    converter = UnifiedLogConverter()

    physical_cores = max(1, (os.cpu_count() or 1) // 2)

    if is_logarchive:
        size = _dir_size(target)
        tracev3 = _count_tracev3(target)
        effective_workers = args.workers if args.workers is not None else physical_cores
        effective_workers = min(effective_workers, tracev3) if tracev3 else 1
        workers_label = str(effective_workers) + (" (baseline)" if effective_workers == 1 else " (parallel)")
        print("\nMode       : logarchive")
        print(f"Path       : {target}")
        print(f"Size       : {_fmt_bytes(size)}")
        print(f"Tracev3    : {tracev3} files in Persist/")
        print(f"Workers    : {workers_label}")
        print("Running conversion … (this may take several minutes)\n")
        t0 = time.perf_counter()
        entry_count = sum(1 for _ in converter.stream_entries(node, vfs, n_workers=args.workers))
    elif is_ios_diagnostics_node(node):
        size = _dir_size(target)
        tracev3 = _count_tracev3(target)
        effective_workers = args.workers if args.workers is not None else physical_cores
        effective_workers = min(effective_workers, tracev3) if tracev3 else 1
        workers_label = str(effective_workers) + (" (baseline)" if effective_workers == 1 else " (parallel)")
        print("\nMode       : iOS FFS diagnostics")
        print(f"Path       : {target}")
        print(f"Size       : {_fmt_bytes(size)}")
        print(f"Tracev3    : {tracev3} files in Persist/")
        print(f"Workers    : {workers_label}")
        print("Running conversion … (this may take several minutes)\n")
        t0 = time.perf_counter()
        entry_count = sum(
            1 for _ in converter.stream_entries_from_diagnostics(node, vfs, n_workers=args.workers)
        )
    else:
        print(
            f"Error: {target.name} is neither a .logarchive nor a recognised "
            f"iOS diagnostics directory (needs Persist/, Special/, or timesync/ children)."
        )
        sys.exit(1)

    duration = time.perf_counter() - t0
    throughput = entry_count / duration if duration > 0 else 0

    print(f"Entries    : {entry_count:,}")
    print(f"Duration   : {duration:.1f} s")
    print(f"Throughput : {throughput:,.0f} entries/s")
    print()


if __name__ == "__main__":
    main()
