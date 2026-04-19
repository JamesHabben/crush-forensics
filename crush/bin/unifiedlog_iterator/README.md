# unifiedlog_iterator binaries

This directory holds the platform-appropriate binaries of Mandiant's
**macos-UnifiedLogs** project, used by Crush to convert binary Apple
Unified Log files (`.tracev3` / `.logarchive`) to JSON.

- **Project:** https://github.com/mandiant/macos-UnifiedLogs
- **Licence:** Apache 2.0 (same as Crush)
- **Version bundled:** v0.5.1

## Expected filenames

| Platform | Filename |
|---|---|
| Linux x86\_64 | `unifiedlog_iterator-x86_64-unknown-linux-gnu` |
| Linux aarch64 | `unifiedlog_iterator-aarch64-unknown-linux-gnu` |
| macOS x86\_64 | `unifiedlog_iterator-x86_64-apple-darwin` |
| macOS arm64   | `unifiedlog_iterator-aarch64-apple-darwin` |
| Windows x86\_64 | `unifiedlog_iterator-x86_64-pc-windows-msvc.exe` |

## Downloading

Run the helper script from the repository root:

```bash
python scripts/download_unifiedlog_binaries.py
```

This downloads all five platform binaries from the GitHub Releases page
and places them in this directory with the correct filenames.

Alternatively, download the release archive for your platform manually from
https://github.com/mandiant/macos-UnifiedLogs/releases and copy the
`unifiedlog_iterator` binary here with the filename shown in the table above.

## Why binaries are not committed to git

The binaries are 2–5 MB each (∼15 MB total for all platforms) and are
pre-built artifacts that change rarely.  Committing them would bloat the
repository history permanently.  The download script fetches the exact
version pinned in `scripts/download_unifiedlog_binaries.py`.
