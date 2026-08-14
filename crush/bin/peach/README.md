# peach-forensics binaries

This directory holds the platform-appropriate binaries of **peach-forensics**,
the sibling forensic log viewer Crush hands AUL (Apple Unified Log) sources
off to via a one-shot CLI spawn (`--add-source`/`--cleanup-dir`) — no IPC
after launch, peach runs completely independently once started.

- **Project:** https://github.com/kalink0/peach-forensics
- **Licence:** Apache 2.0 (same as Crush)
- **Version bundled:** v0.1.0 — pinned in `scripts/download_peach_binaries.py`'s
  `VERSION` constant, same pattern as `crush/bin/unifiedlog_iterator/`'s
  `UL_VERSION`. Bump that constant when upgrading.

## Expected filenames

| Platform | Filename |
|---|---|
| Linux x86\_64 | `peach-linux` |
| macOS arm64   | `peach-macos-arm` |
| macOS x86\_64 | `peach-macos-intel` |
| Windows x86\_64 | `peach-windows.exe` |

## Downloading

Run the helper script from the repository root:

```bash
python scripts/download_peach_binaries.py
```

This downloads all four platform binaries from the pinned release version
and places them in this directory with the correct filenames.

## Why binaries are not committed to git

Same reasoning as `crush/bin/unifiedlog_iterator/` — pre-built artifacts,
tens of MB total, would bloat repository history permanently if committed.
