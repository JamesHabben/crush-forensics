# crush-forensics

Crush — Digital Forensic Analysis Workbench

## System Dependencies

Some Python packages require OS-level libraries on fresh machines.

### libmagic (for `python-magic`)

`python-magic` depends on `libmagic` being present on the system.

- Debian/Ubuntu: `sudo apt-get install libmagic1`
- Fedora: `sudo dnf install file-libs`
- Arch: `sudo pacman -S file`
- macOS (Homebrew): `brew install libmagic`

### Qt Multimedia (for audio/video)

`PySide6` uses system multimedia backends.

- Debian/Ubuntu: `sudo apt-get install gstreamer1.0-plugins-base gstreamer1.0-plugins-good`
- Fedora: `sudo dnf install gstreamer1-plugins-base gstreamer1-plugins-good`
- Arch: `sudo pacman -S gstreamer gst-plugins-base gst-plugins-good`
- macOS: typically bundled with Qt; if media playback fails, install `gstreamer`.
