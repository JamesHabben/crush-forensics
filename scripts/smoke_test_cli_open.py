#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Manual smoke test for CLI-based evidence loading (crush PATH / --open PATH, #45/#46).

Invokes `crush` as a subprocess, exactly like an external caller would — no
internal crush imports here, just the command-line entry point itself. Falls
back to `python -m crush` if `crush` isn't on PATH.

Usage:
    python scripts/smoke_test_cli_open.py /path/to/your/evidence
    python scripts/smoke_test_cli_open.py /path/to/a --open /path/to/b
"""
from __future__ import annotations

import shutil
import subprocess
import sys


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(f"Usage: python {sys.argv[0]} PATH [PATH ...] [--open PATH ...]", file=sys.stderr)
        raise SystemExit(1)

    crush_exe = shutil.which("crush")
    command = [crush_exe] if crush_exe else [sys.executable, "-m", "crush"]
    print(f"Running: {' '.join(command + args)}")
    subprocess.run(command + args, check=True)


if __name__ == "__main__":
    main()
