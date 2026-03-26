# crush-forensics

Crush — Digital Forensic Analysis Workbench

[![CI](https://github.com/kalink0/crush-forensics/actions/workflows/ci.yml/badge.svg)](https://github.com/kalink0/crush-forensics/actions/workflows/ci.yml)
![Linux](https://img.shields.io/badge/linux-supported-success)
![Windows](https://img.shields.io/badge/windows-supported-success)
[![Release](https://img.shields.io/github/v/release/kalink0/crush-forensics?display_name=tag)](https://github.com/kalink0/crush-forensics/releases)
[![License](https://img.shields.io/github/license/kalink0/crush-forensics)](https://github.com/kalink0/crush-forensics/blob/main/LICENSE)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)

## Features

Open and navigate in ZIP and TAR archives (eg. for mobile phone acquisitions).
Open single files and folder.

When navigating and open file you can use the currently supported viewers (more planned):

- ABX Viewer
- Hex Viewer
- SQLITE Viewer
- SEGB v1/v2 Decoder and Viewer
- Media file (Audio, Video Image) Viewer
- JSON Viewer
- XML-Viewer
- PLIST and BPLIST Viewer

## Screenshots

Android ABX (Linux)
![Android ABX (Linux)](crush/docs/pictures/example_android_lin_abx.png)

Android Video (Linux)
![Android Video (Linux)](crush/docs/pictures/example_android_lin_video.png)

Loading Speed - How fast we can load from zips
![Loading Speed](crush/docs/pictures/example_ios_lin_ingest_speed.png)

iOS SEGB (Windows)
![iOS SEGB (Windows)](crush/docs/pictures/example_ios_win_segb.png)

iOS SQLite Summary (Windows)
![iOS SQLite Summary (Windows)](crush/docs/pictures/example_ios_win_sqlite_summary.png)

Format Reference (Linux)
![Format Reference (Linux)](crush/docs/pictures/example_lin_file_formats.png)

## Install and Run

### From source (recommended for development)

1. Create a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies
```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

3. Run Crush
```bash
crush
```

### Alternative run command

```bash
python -m crush
```

If you see missing Qt or media errors, install the system dependencies below.

## System Dependencies

Some Python packages require OS-level libraries on fresh machines.

### Base GUI/Qt runtime (PySide6)

These are required for the Qt GUI to run correctly on Linux.

- Debian/Ubuntu: `sudo apt-get install libgl1 libegl1 libxcb-xinerama0 libxkbcommon-x11-0`
- Fedora: `sudo dnf install mesa-libGL mesa-libEGL libxcb libxkbcommon-x11`
- Arch: `sudo pacman -S mesa libglvnd libxcb libxkbcommon-x11`
- Windows: no additional packages required; if the app fails to start, install the Microsoft Visual C++ Redistributable 2015-2022 (x64)
- macOS: no additional packages required (bundled with the OS)

### libmagic (for `python-magic`)

`python-magic` depends on `libmagic` being present on the system.

- Debian/Ubuntu: `sudo apt-get install libmagic1`
- Fedora: `sudo dnf install file-libs`
- Arch: `sudo pacman -S file`
- macOS (Homebrew): `brew install libmagic`
- Windows: no additional packages required

### Qt Multimedia (for audio/video)

`PySide6` uses system multimedia backends.

- Debian/Ubuntu: `sudo apt-get install gstreamer1.0-plugins-base gstreamer1.0-plugins-good`
- Fedora: `sudo dnf install gstreamer1-plugins-base gstreamer1-plugins-good`
- Arch: `sudo pacman -S gstreamer gst-plugins-base gst-plugins-good`
- macOS: typically bundled with Qt; if media playback fails, install `gstreamer`
- Windows: typically bundled with Qt; no additional packages required

### Audio backend (PulseAudio)

For Linux audio playback, `libpulse` is commonly required by Qt Multimedia.

- Debian/Ubuntu: `sudo apt-get install libpulse0`
- Fedora: `sudo dnf install pulseaudio-libs`
- Arch: `sudo pacman -S libpulse`

## Acknowledgements

This project builds on the great work of the DFIR community. The following third-party modules by [CCL Solutions Group](https://github.com/cclgroupltd) are bundled:

- [ccl_bplist](https://github.com/cclgroupltd/ccl-bplist) — Binary plist module (BSD 3-Clause)
- [ccl_segb](https://github.com/cclgroupltd/ccl_segb) — SEGB (Significant Energy Bearer) module (MIT)
- [ccl_leveldb](https://github.com/cclgroupltd/ccl-leveldb) — LevelDB / Chrome LevelDB module (MIT)

Parts of this software were developed with assistance from [Claude AI / Claude Code](https://claude.ai) by Anthropic.
