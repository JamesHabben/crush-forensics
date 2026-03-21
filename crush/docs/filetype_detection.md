# Filetype Detection

This document describes how Crush identifies file types during tree building and when opening files.

## Overview

Crush uses a two-step detection pipeline:

1. **Fast detection** (header sniff)
   - We call `filetype.guess()` on a small byte prefix.
   - If it returns a known type, we map it to a quick label:
     - `image/*` → `Image`
     - `audio/*` / `video/*` → `Media`
     - otherwise we show the detected extension in uppercase (e.g., `PDF`, `ZIP`).

2. **Fallback detection** (Crush-specific logic)
   - If `filetype` does not recognize the file, we run our own lightweight checks.
   - If still unknown, we fall back to the parser registry (which may run deeper checks).

## Custom Fast Magics (Crush)

These are the custom checks we run when `filetype` returns no match:

- **SQLite**  
  - Magic: `SQLite format 3\0`

- **Binary plist (bplist)**  
  - Magic: `bplist`

- **Android Binary XML (ABX)**  
  - Magic: `ABX\0`

- **SEGB (v1/v2)**  
  - Magic: `SEGB`

- **XML plist**  
  - Begins with `<?xml` and root tag is `<plist>`  
  - File extensions are treated as hints only, not as evidence

## Fallback: Parser Registry

If no fast detection hits, we defer to the parser registry (priority order). Parsers can use:

- extended header checks
- extensions
- directory structure (e.g., LevelDB)
- full parsing for validation

This keeps the UI fast while still allowing deep format detection where needed.
