# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Build script — regenerates formats.db from the FORMATS list below.

Run from the project root:
    python -m crush.data.build_formats_db

This is the single source of truth for all format knowledge.
Parsers carry no metadata — format info lives here only.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

_OUT = Path(__file__).parent / "formats.db"

# ---------------------------------------------------------------------------
# Format definitions
# Each entry:
#   name            Full human-readable name
#   short_name      Abbreviation shown in UI
#   category        database | configuration | log | execution | document |
#                   filesystem | disk_image | archive | serialization |
#                   memory | network | uncategorized
#   forensic_relevance  What an investigator would find here
#   platforms       List of strings: "iOS", "macOS", "Android", "Windows", "Linux"
#   parser_class    Class name in crush/parsers/ that handles this, or None
#   magic           List of dicts: {"offset": int | None, "value": bytes,
#                                   "description": str}
#                   All entries must match for a hit. Use offset=None for
#                   trailer/unknown offsets (informational only).
#   extensions      List of lowercase extensions including the dot
#   links           List of (label, url) tuples — reference links
#   status          "draft" (excluded from DB) | "reviewed" (included in DB)
# ---------------------------------------------------------------------------

FORMATS: list[dict[str, Any]] = [
    {
        "name": "Android Binary XML (ABX)",
        "short_name": "ABX",
        "category": "configuration",
        "forensic_relevance": (
            "Android system and app settings stored as compact binary XML."
        ),
        "platforms": ["Android"],
        "parser_class": "AbxParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x41\x42\x58\x00",
                "description": "Android Binary XML header",
            }
        ],
        "extensions": [".xml", ".abx"],
        "links": [
            (
                "AOSP source (Code Search)",
                "https://cs.android.com/android/platform/superproject/main/+/main:frameworks/libs/modules-utils/java/com/android/modules/utils/BinaryXmlSerializer.java",
            ),
            ("Research", "https://www.cclsolutionsgroup.com/post/android-abx-binary-xml"),
        ],
        "status": "reviewed",
    },
    {
        "name": "Android Backup Archive",
        "short_name": "Android backup",
        "category": "archive",
        "forensic_relevance": (
            "Backup of mobile phone acquired via ADB backup functionality."
            ""
        ),
        "platforms": ["Android"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x41\x4e\x44\x52\x4f\x49\x44\x20\x42\x41\x43\x4b\x55\x50\x0a",
                "description": "Android backup header",
            }
        ],
        "extensions": [".ab"],
        "links": [
            (
                "AOSP source",
                "https://android.googlesource.com/platform/frameworks/base/+/refs/heads/jb-dev/services/java/com/android/server/BackupManagerService.java",
            ),
            (
                "Android Backup Extractor (ABE)",
                "https://github.com/nelenkov/android-backup-extractor",
            ),
            (
                "Research",
                "https://nelenkov.blogspot.com/2012/06/unpacking-android-backups.html",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "Binary Property List",
        "short_name": "bplist",
        "category": "configuration",
        "forensic_relevance": (
            "App preferences, caches, configuration, and iOS backup structures "
            "such as Manifest.plist and Info.plist."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": "PlistParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x62\x70\x6c\x69\x73\x74",
                "description": "Binary plist magic",
            }
        ],
        "extensions": [".plist"],
        "links": [
            (
                "Developer docs (binary format)",
                "https://developer.apple.com/documentation/foundation/propertylistserialization/propertylistformat/binary",
            ),
            (
                "Developer docs (Property Lists)",
                "https://developer.apple.com/library/archive/documentation/CoreFoundation/Conceptual/CFPropertyLists/",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "CBOR (Concise Binary Object Representation)",
        "short_name": "CBOR",
        "category": "serialization",
        "forensic_relevance": (
            "RFC 8949 binary format used in modern APIs and WebAuthn/FIDO2 "
            "credential storage. Increasingly common in security-relevant app data."
        ),
        "platforms": ["iOS", "macOS", "Android"],
        "parser_class": None,
        "magic": [],
        "extensions": [".cbor"],
        "links": [
            ("Format spec (RFC 8949)", "https://www.rfc-editor.org/rfc/rfc8949.html"),
            ("Overview", "https://cbor.io/"),
        ],
        "status": "reviewed",
    },
    {
        "name": "Realm Database",
        "short_name": "Realm",
        "category": "database",
        "forensic_relevance": (
            "Mobile app local object store used as a SQLite replacement. "
            "A single '.realm' file stores all object data in a B+ tree of fixed-size "
            "arrays. Crush extracts the full schema (class/table names such as "
            "'class_Driver', 'class_Event', 'class_Photo') and decodes both root "
            "references (top_ref[0] / top_ref[1]) that act as a WAL-like journaling "
            "pair — the inactive branch may contain superseded data not yet checkpointed. "
            "Class names reveal which app features were in use and what data categories "
            "are present (users, locations, media, events, etc.)."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows", "Linux"],
        "parser_class": "RealmParser",
        "magic": [
            {
                "offset": 16,
                "value": b"\x54\x2d\x44\x42",
                "description": "Realm header mnemonic (T-DB)",
            }
        ],
        "extensions": [".realm"],
        "links": [
            (
                "Realm files (database internals)",
                "https://mongodben.github.io/flutter-sdk-docs/sdk/flutter/realm-database",
            ),
            (
                "Open a Realm file (Realm Studio)",
                "https://www.mongodb.com/docs/atlas/device-sdks/studio/open-realm-file/",
            ),
            (
                "Default Realm file URL (Swift Configuration)",
                "https://www.mongodb.com/docs/realm-sdks/swift/10.9.0/Structs/Realm/Configuration.html",
            ),
            (
                "The Realm Files - Vol 3 - The Realm Header (Damien Attoe)",
                "https://digital4n6withdamien.blogspot.com/2026/01/the-realm-files-vol-3-realm-header.html",
            ),
            (
                "The Realm Files - Vol 2 - Physical Structure Overview (Damien Attoe)",
                "https://digital4n6withdamien.blogspot.com/2025/11/the-realm-files-vol-2-physical.html",
            ),
            (
                "Mobile App Forensics: A Practical Guide (Realm file format)",
                "https://link.springer.com/content/pdf/10.1007/978-3-030-98467-0_8",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "Android DEX Bytecode",
        "short_name": "DEX",
        "category": "execution",
        "forensic_relevance": (
            "Compiled Android application code. Can be decompiled to recover "
            "app logic, hardcoded credentials, and API endpoints."
        ),
        "platforms": ["Android"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x64\x65\x78\x0a",
                "description": "DEX magic",
            }
        ],
        "extensions": [".dex"],
        "links": [("AOSP source", "https://source.android.com/docs/core/runtime/dex-format")],
        "status": "reviewed",
    },
    {
        "name": "Apple Disk Image (DMG)",
        "short_name": "DMG",
        "category": "disk_image",
        "forensic_relevance": (
            "macOS disk image format used for app distribution and backups. "
            "May contain HFS+ or APFS filesystems requiring separate mounting."
        ),
        "platforms": ["macOS"],
        "parser_class": None,
        "magic": [
            {
                "offset": None,
                "value": b"\x6b\x6f\x6c\x79",
                "description": "DMG trailer magic (koly block) at EOF-512",
            }
        ],
        "extensions": [".dmg"],
        "links": [("Research", "https://newosxbook.com/DMG.html")],
        "status": "reviewed",
    },
    {
        "name": "ELF Executable",
        "short_name": "ELF",
        "category": "execution",
        "forensic_relevance": (
            "Android and Linux native executable format. "
        ),
        "platforms": ["Android", "Linux"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x7f\x45\x4c\x46",
                "description": "ELF magic number",
            }
        ],
        "extensions": [".so", ".elf"],
        "links": [("Format spec", "https://man7.org/linux/man-pages/man5/elf.5.html")],
        "status": "reviewed",
    },
    {
        "name": "Windows Event Log (EVTX)",
        "short_name": "EVTX",
        "category": "log",
        "forensic_relevance": (
            "Windows structured event logs. Contains security events, logons, "
            "process creation, PowerShell activity, system errors and more."
        ),
        "platforms": ["Windows"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x45\x6c\x66\x46\x69\x6c\x65\x00",
                "description": "EVTX file signature",
            }
        ],
        "extensions": [".evtx"],
        "links": [("Format spec", "https://github.com/libyal/libevtx/blob/main/documentation/Windows%20XML%20Event%20Log%20(EVTX).asciidoc")],
        "status": "reviewed",
    },
    {
        "name": "JPEG Image",
        "short_name": "JPEG",
        "category": "document",
        "forensic_relevance": (
            "Photos and screenshots from device cameras and apps. "
            "Can contain EXIF metadata including GPS coordinates, timestamps, "
            "device model, and camera settings."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows", "Linux"],
        "parser_class": "ImageParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\xff\xd8\xff",
                "description": "JPEG SOI marker",
            }
        ],
        "extensions": [".jpg", ".jpeg"],
        "links": [
            ("Format spec (JPEG / ITU-T T.81)", "https://www.itu.int/rec/T-REC-T.81/en"),
            ("Exif spec (CIPA DC-008)", "https://www.cipa.jp/e/std/std-sec.html"),
        ],
        "status": "reviewed",
    },
    {
        "name": "PNG Image",
        "short_name": "PNG",
        "category": "document",
        "forensic_relevance": (
            "Screenshots, app icons, and lossless images. "
            "Can embed tEXt/iTXt metadata chunks with creation info and comments."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "ImageParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a",
                "description": "PNG signature",
            }
        ],
        "extensions": [".png"],
        "links": [("Format spec", "https://www.w3.org/TR/PNG/")],
        "status": "reviewed",
    },
    {
        "name": "GIF Image",
        "short_name": "GIF",
        "category": "document",
        "forensic_relevance": (
            "Animated and static images e.g. sent via messaging apps and stored "
            "in browser caches. Can contain comment extensions with metadata."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "ImageParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x47\x49\x46\x38\x37\x61",
                "description": "GIF87a header",
            },
            {
                "offset": 0,
                "value": b"\x47\x49\x46\x38\x39\x61",
                "description": "GIF89a header (animated GIF support)",
            },
        ],
        "extensions": [".gif"],
        "links": [("Format spec", "https://www.w3.org/Graphics/GIF/spec-gif89a.txt")],
        "status": "reviewed",
    },
    {
        "name": "BMP Image",
        "short_name": "BMP",
        "category": "document",
        "forensic_relevance": (
            "Uncompressed bitmap format common in Windows apps and legacy software. "
            "No metadata compression — raw pixel data may reveal screen content."
        ),
        "platforms": ["Windows", "Android"],
        "parser_class": "ImageParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x42\x4d",
                "description": "BMP file header signature",
            }
        ],
        "extensions": [".bmp"],
        "links": [  ("Format spec", "https://learn.microsoft.com/en-us/windows/win32/gdi/bitmap-storage"),
                    ("Format Spec", "https://en.wikipedia.org/wiki/BMP_file_format")
        ],
        "status": "reviewed",
    },
    {
        "name": "TIFF Image",
        "short_name": "TIFF",
        "category": "document",
        "forensic_relevance": (
            "High-quality scans and camera RAW derivatives. "
            "Supports extensive EXIF/XMP metadata and GPS tags. "
            "Used in document scanning and professional workflows."
        ),
        "platforms": ["iOS", "macOS", "Windows"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x49\x49\x2a\x00",
                "description": "TIFF little-endian (Intel byte order)",
            },
            {
                "offset": 0,
                "value": b"\x4d\x4d\x00\x2a",
                "description": "TIFF big-endian (Motorola byte order)",
            },
        ],
        "extensions": [".tif", ".tiff"],
        "links": [("Format spec", "https://www.adobe.io/content/dam/udp/en/open/standards/tiff/TIFF6.pdf")],
        "status": "reviewed",
    },
    {
        "name": "WebP Image",
        "short_name": "WebP",
        "category": "document",
        "forensic_relevance": (
            "Modern image format used by Chrome, Android, and web apps for "
            "compressed photos and stickers. Supports EXIF and XMP metadata."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "ImageParser",
        "magic": [
            {
                "offset": 8,
                "value": b"\x57\x45\x42\x50",
                "description": "WebP signature within RIFF container (offset 8)",
            }
        ],
        "extensions": [".webp"],
        "links": [("Format spec", "https://developers.google.com/speed/webp/docs/riff_container")],
        "status": "reviewed",
    },
    {
        "name": "HEIC / HEIF Image",
        "short_name": "HEIC/HEIF",
        "category": "document",
        "forensic_relevance": (
            "Default photo format on iOS 11+. Supported by Android since version 8"
            "Can Contain rich EXIF metadata including GPS, timestamps, and device info. "
            "HEIF is the container; HEVC is the codec."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": None,
        "magic": [
            {
                "offset": 4,
                "value": b"\x66\x74\x79\x70",
                "description": "ISOBMFF ftyp box (offset 4)",
            },
            {
                "offset": 8,
                "value": b"\x68\x65\x69\x63",
                "description": "HEIC brand identifier (offset 8)",
            },
        ],
        "extensions": [".heic", ".heif"],
        "links": [
            ("Developer docs", "https://developer.apple.com/documentation/imageio"),
            ("Format spec", "https://nokiatech.github.io/heif/"),
        ],
        "status": "reviewed",
    },
    {
        "name": "iOS Crash Report",
        "short_name": "IPS / crash",
        "category": "log",
        "forensic_relevance": (
            "Application crash reports with stack traces, thread states, "
            "and exception details. Indicate app instability or exploitation attempts."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": None,
        "magic": [],
        "extensions": [".ips", ".crash"],
        "links": [("Developer docs", "https://developer.apple.com/documentation/xcode/examining-the-fields-in-a-crash-report")],
        "status": "draft",
    },
    {
        "name": "JSON Document",
        "short_name": "JSON",
        "category": "serialization",
        "forensic_relevance": (
            "App configuration, API responses cached on device, "
            "browser storage, and exported data from many modern apps."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "JsonParser",
        "magic": [],
        "extensions": [".json", ".geojson", ".jsonl", ".ndjson"],
        "links": [("Format spec", "https://datatracker.ietf.org/doc/html/rfc8259")],
        "status": "reviewed",
    },
    {
        "name": "LevelDB Database",
        "short_name": "LevelDB",
        "category": "database",
        "forensic_relevance": (
            "Key-value store used by Chrome, browsers, Electron Apps " 
            "and many Android/iOS apps "
            "for caches, IndexedDB, and app state."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "LeveldbParser",
        "magic": [],
        "extensions": [".ldb", ".log"],
        "links": [( "Format spec", "https://github.com/google/leveldb/blob/main/doc/impl.md"),
                  ( "Blog Post", "https://www.cclsolutionsgroup.com/post/hang-on-thats-not-sqlite-chrome-electron-and-leveldb"),
        ],
        "status": "reviewed",
    },
    {
        "name": "Unified Log Archive (logarchive)",
        "short_name": "logarchive",
        "category": "log",
        "forensic_relevance": (
            "Packaged collection of tracev3 log files and UUID maps. "
            "Primary log artifact from sysdiagnose captures."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": None,
        "magic": [],
        "extensions": [".logarchive"],
        "links": [("Source code", "https://github.com/mandiant/macos-UnifiedLogs")],
        "status": "draft",
    },
    {
        "name": "LZFSE Compressed Data",
        "short_name": "LZFSE",
        "category": "archive",
        "forensic_relevance": (
            "Apple-proprietary compression used in iOS 9+ system files, "
            "OTA updates, and some app data."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x62\x76\x78\x32",
                "description": "LZFSE magic",
            }
        ],
        "extensions": [],
        "links": [("Source code", "https://github.com/lzfse/lzfse")],
        "status": "draft",
    },
    {
        "name": "Mach-O Executable",
        "short_name": "Mach-O",
        "category": "execution",
        "forensic_relevance": (
            "iOS and macOS native executable format. App binaries can be analysed "
            "for hardcoded strings, URLs, encryption keys, and entitlements."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\xce\xfa\xed\xfe",
                "description": "Mach-O 32-bit magic (little-endian)",
            }
        ],
        "extensions": ["", ".dylib", ".framework"],
        "links": [("Developer docs", "https://developer.apple.com/library/archive/documentation/Performance/Conceptual/CodeFootprint/Articles/MachOOverview.html")],
        "status": "draft",
    },
    {
        "name": "MP4 Video",
        "short_name": "MP4",
        "category": "document",
        "forensic_relevance": (
            "Screen recordings, downloaded videos, and app media. "
            "MP4 containers carry timestamps and may embed GPS tracks and device metadata."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 4,
                "value": b"\x66\x74\x79\x70",
                "description": "ISOBMFF ftyp box (offset 4)",
            }
        ],
        "extensions": [".mp4", ".m4v"],
        "links": [("Format spec", "https://en.wikipedia.org/wiki/MP4_file_format")],
        "status": "reviewed",
    },
    {
        "name": "MOV Video (QuickTime)",
        "short_name": "MOV",
        "category": "document",
        "forensic_relevance": (
            "Video recordings from iOS cameras and macOS screen recordings. "
            "QuickTime containers embed creation timestamps and GPS metadata."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 4,
                "value": b"\x66\x74\x79\x70",
                "description": "ISOBMFF ftyp box (offset 4)",
            },
            {
                "offset": 8,
                "value": b"\x71\x74\x20\x20",
                "description": "QuickTime brand identifier (offset 8)",
            },
        ],
        "extensions": [".mov"],
        "links": [("Format spec", "https://developer.apple.com/library/archive/documentation/QuickTime/QTFF/QTFFPreface/qtffPreface.html")],
        "status": "reviewed",
    },
    {
        "name": "AVI Video",
        "short_name": "AVI",
        "category": "document",
        "forensic_relevance": (
            "Legacy Windows video format found in older recordings and surveillance footage. "
            "May contain metadata in INFO chunks."
        ),
        "platforms": ["Windows", "Android"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x52\x49\x46\x46",
                "description": "RIFF container header",
            },
            {
                "offset": 8,
                "value": b"\x41\x56\x49\x20",
                "description": "AVI subtype identifier (offset 8)",
            },
        ],
        "extensions": [".avi"],
        "links": [("Format spec", "https://learn.microsoft.com/en-us/windows/win32/directshow/avi-riff-file-reference")],
        "status": "reviewed",
    },
    {
        "name": "MKV Video (Matroska)",
        "short_name": "MKV",
        "category": "document",
        "forensic_relevance": (
            "Open container format for HD video found in downloads, screen recordings, "
            "and media apps. Supports chapters, subtitles, and multiple tracks."
        ),
        "platforms": ["Android", "Windows", "Linux"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x1a\x45\xdf\xa3",
                "description": "EBML header (Matroska/WebM)",
            }
        ],
        "extensions": [".mkv"],
        "links": [("Format spec", "https://www.matroska.org/technical/basics.html")],
        "status": "reviewed",
    },
    {
        "name": "WebM Video",
        "short_name": "WebM",
        "category": "document",
        "forensic_relevance": (
            "Web-optimised video format used in browsers and Android apps. "
            "Based on the Matroska container with VP8/VP9/AV1 video."
        ),
        "platforms": ["Android", "Windows", "Linux"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x1a\x45\xdf\xa3",
                "description": "EBML header (Matroska/WebM)",
            }
        ],
        "extensions": [".webm"],
        "links": [("Format spec", "https://www.webmproject.org/")],
        "status": "reviewed",
    },
    {
        "name": "3GP / 3G2 Video",
        "short_name": "3GP",
        "category": "document",
        "forensic_relevance": (
            "Video format used by older mobile devices for camera recordings "
            "and MMS. Common in Android and older iOS devices."
        ),
        "platforms": ["Android", "iOS"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 4,
                "value": b"\x66\x74\x79\x70",
                "description": "ISOBMFF ftyp box (offset 4)",
            }
        ],
        "extensions": [".3gp", ".3g2"],
        "links": [("Format spec", "https://www.3gpp.org/ftp/Specs/archive/26_series/26.244/")],
        "status": "reviewed",
    },
    {
        "name": "MP3 Audio",
        "short_name": "MP3",
        "category": "document",
        "forensic_relevance": (
            "Common audio format for music, voicemails, and voice memos. "
            "ID3 tags embed title, artist, album, and sometimes geolocation."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x49\x44\x33",
                "description": "ID3 tag header (MP3 with metadata)",
            },
            {
                "offset": 0,
                "value": b"\xff\xfb",
                "description": "MPEG-1 Layer 3 sync word (no ID3 header)",
            },
        ],
        "extensions": [".mp3"],
        "links": [("ID3 spec", "https://id3.org/id3v2.3.0"),
                  ("Format spec", "https://en.wikipedia.org/wiki/MP3")],
        "status": "reviewed",
    },
    {
        "name": "WAV Audio",
        "short_name": "WAV",
        "category": "document",
        "forensic_relevance": (
            "Uncompressed audio used for voice recordings, call recordings."
            "INFO chunks may contain metadata."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x52\x49\x46\x46",
                "description": "RIFF container header",
            },
            {
                "offset": 8,
                "value": b"\x57\x41\x56\x45",
                "description": "WAVE subtype identifier (offset 8)",
            },
        ],
        "extensions": [".wav"],
        "links": [("Format spec", "https://www.iana.org/assignments/wave-avi-codec-registry/wave-avi-codec-registry.xhtml")],
        "status": "reviewed",
    },
    {
        "name": "M4A Audio (MPEG-4 Audio)",
        "short_name": "M4A",
        "category": "document",
        "forensic_relevance": (
            "AAC audio in an MPEG-4 container. Used for purchased music, "
            "voice memos, and FaceTime audio recordings on Apple devices."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 4,
                "value": b"\x66\x74\x79\x70",
                "description": "ISOBMFF ftyp box (offset 4)",
            },
            {
                "offset": 8,
                "value": b"\x4d\x34\x41\x20",
                "description": "M4A brand identifier (offset 8)",
            },
        ],
        "extensions": [".m4a"],
        "links": [("Format spec", "https://en.wikipedia.org/wiki/MP4_file_format")],
        "status": "reviewed",
    },
    {
        "name": "AAC Audio",
        "short_name": "AAC",
        "category": "document",
        "forensic_relevance": (
            "Raw AAC audio stream without container. Used in streaming, "
            "broadcasting, and some messaging app voice messages."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\xff\xf1",
                "description": "ADTS sync word (AAC-LC)",
            },
            {
                "offset": 0,
                "value": b"\xff\xf9",
                "description": "ADTS sync word (AAC-LC, MPEG-2)",
            },
        ],
        "extensions": [".aac"],
        "links": [("Format spec", "https://en.wikipedia.org/wiki/Advanced_Audio_Coding")],
        "status": "draft",
    },
    {
        "name": "FLAC Audio",
        "short_name": "FLAC",
        "category": "document",
        "forensic_relevance": (
            "Lossless compressed audio common in music libraries and high-quality "
            "recordings. FLAC tags carry rich metadata including timestamps."
        ),
        "platforms": ["Android", "Windows", "macOS", "Linux"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x66\x4c\x61\x43",
                "description": "FLAC stream marker",
            }
        ],
        "extensions": [".flac"],
        "links": [("Format spec", "https://xiph.org/flac/format.html")],
        "status": "reviewed",
    },
    {
        "name": "OGG Audio",
        "short_name": "OGG",
        "category": "document",
        "forensic_relevance": (
            "Ogg Vorbis audio container used by some Android apps and media players. "
            "Comment headers store artist, title, and encoder metadata."
        ),
        "platforms": ["Android", "Linux"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x4f\x67\x67\x53",
                "description": "Ogg page capture pattern",
            }
        ],
        "extensions": [".ogg"],
        "links": [("Format spec", "https://xiph.org/ogg/")],
        "status": "reviewed",
    },
    {
        "name": "Opus Audio",
        "short_name": "Opus",
        "category": "document",
        "forensic_relevance": (
            "Low-latency audio codec used in WhatsApp, Signal, Telegram, and "
            "WebRTC voice messages. Stored in an Ogg container."
        ),
        "platforms": ["Android", "iOS", "Windows"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x4f\x67\x67\x53",
                "description": "Ogg container (Opus uses Ogg as transport)",
            }
        ],
        "extensions": [".opus"],
        "links": [("Format spec", "https://opus-codec.org/docs/")],
        "status": "reviewed",
    },
    {
        "name": "WMA Audio (Windows Media Audio)",
        "short_name": "WMA",
        "category": "document",
        "forensic_relevance": (
            "Windows-native audio format found on Windows devices and older "
            "smartphones. ASF container may carry DRM licensing information."
        ),
        "platforms": ["Windows"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x30\x26\xb2\x75",
                "description": "ASF header object GUID (first 4 bytes)",
            }
        ],
        "extensions": [".wma"],
        "links": [("Format spec", "https://learn.microsoft.com/en-us/windows/win32/wmformat/windows-media-format-sdk")],
        "status": "draft",
    },
    {
        "name": "AMR Audio",
        "short_name": "AMR",
        "category": "document",
        "forensic_relevance": (
            "Adaptive Multi-Rate audio used for call recordings and voice memos "
            "on Android and older iOS devices. Common in telecommunication evidence."
        ),
        "platforms": ["Android", "iOS"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x23\x21\x41\x4d\x52",
                "description": "AMR-NB file header",
            }
        ],
        "extensions": [".amr"],
        "links": [("Format spec", "https://www.ietf.org/rfc/rfc3267.txt")],
        "status": "draft",
    },
    {
        "name": "MessagePack",
        "short_name": "msgpack",
        "category": "serialization",
        "forensic_relevance": (
            "Compact binary serialization used by some messaging and social apps "
            "for caching and inter-process communication."
        ),
        "platforms": ["iOS", "macOS", "Android"],
        "parser_class": None,
        "magic": [],
        "extensions": [".msgpack", ".mp"],
        "links": [("Format spec", "https://msgpack.org/index.html")],
        "status": "draft",
    },
    {
        "name": "NSKeyedArchiver Archive",
        "short_name": "NSKeyedArchiver",
        "category": "serialization",
        "forensic_relevance": (
            "Apple's object graph serialization format used by Messages, Notes, "
            "Health, Contacts, Calendar, Photos, and most third-party iOS/macOS apps "
            "to persist complex data objects. Stored as a binary plist whose root dict "
            "contains '$archiver': 'NSKeyedArchiver' and '$objects' array. "
            "Recovering the object graph can reveal message history, contact data, "
            "health records, and app-specific user content."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x62\x70\x6c\x69\x73\x74",
                "description": "Binary plist container — NSKeyedArchiver identified by $archiver key inside",
            }
        ],
        "extensions": [".plist", ".archive", ".nskeyedarchiver"],
        "links": [
            ("Developer docs", "https://developer.apple.com/documentation/foundation/nskeyedarchiver"),
            ("Blog", "https://www.hexordia.com/blog/khatri-tool-deserialize-nskey"),
        ],
        "status": "draft",
    },
    {
        "name": "Android OAT / ART Compiled Code",
        "short_name": "OAT",
        "category": "execution",
        "forensic_relevance": (
            "ART-compiled versions of DEX files. Presence indicates the app "
            "was installed and executed on the device."
        ),
        "platforms": ["Android"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x6f\x61\x74\x0a",
                "description": "OAT magic",
            }
        ],
        "extensions": [".oat", ".odex", ".vdex"],
        "links": [("AOSP source", "https://source.android.com/docs/core/runtime")],
        "status": "draft",
    },
    {
        "name": "PDF Document",
        "short_name": "PDF",
        "category": "document",
        "forensic_relevance": (
            "Documents, receipts, tickets, and exported reports stored in apps "
            "or transmitted via messaging. May contain metadata, author, and dates."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "PDFParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x25\x50\x44\x46",
                "description": "PDF header",
            }
        ],
        "extensions": [".pdf"],
        "links": [("Format spec", "https://opensource.adobe.com/dc-acrobat-sdk-docs/standards/pdfstandards/pdf/PDF32000_2008.pdf")],
        "status": "draft",
    },
    {
        "name": "Property List",
        "short_name": "plist",
        "category": "configuration",
        "forensic_relevance": (
            "Human-readable XML plist. Used for app preferences, "
            "configuration files, and Info.plist manifests."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": "PlistParser",
        "magic": [],
        "extensions": [".plist"],
        "links": [("Developer docs", "https://developer.apple.com/library/archive/documentation/CoreFoundation/Conceptual/CFPropertyLists/")],
        "status": "reviewed",
    },
    {
        "name": "Protocol Buffers (protobuf)",
        "short_name": "protobuf",
        "category": "serialization",
        "forensic_relevance": (
            "Binary serialization format used by Google apps, Chrome, WhatsApp, "
            "Signal, and many others. Requires .proto schema to decode field names."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "ProtobufParser",
        "magic": [],
        "extensions": [".pb", ".proto"],
        "links": [("Format Documentation", "https://protobuf.dev/programming-guides/encoding/")],
        "status": "reviewed",
    },
    {
        "name": "Windows Registry Hive",
        "short_name": "Registry",
        "category": "database",
        "forensic_relevance": (
            "Windows system and user configuration database. Contains installed "
            "software, user activity, network history, and USB device records."
        ),
        "platforms": ["Windows"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x72\x65\x67\x66",
                "description": "Registry hive signature",
            }
        ],
        "extensions": [".dat", ".hiv"],
        "links": [("Format spec", "https://github.com/msuhanov/regf/blob/master/Windows%20registry%20file%20format%20specification.md")],
        "status": "draft",
    },
    {
        "name": "Apple SEGB (Biome store)",
        "short_name": "SEGB",
        "category": "log",
        "forensic_relevance": (
            "Apple Biome framework data stores. Contains app usage, screen time, "
            "location, health, and Siri interaction history. SEGB was first seen with iOS 13"
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": "SegbParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x53\x45\x47\x42",
                "description": "SEGB v2 Biome store header (magic at start)",
            },
            {
                # SEGB v1: 56-byte header, magic in last 4 bytes at offset 52 (0x34)
                "offset": 52,
                "value": b"\x53\x45\x47\x42",
                "description": "SEGB v1 Biome store header (magic at offset 0x34)",
            },
        ],
        "extensions": [".segb", ".segb1", ".segb2", ".biome"],
        "links": [("3rd Party Parser Source code", "https://github.com/cclgroupltd/ccl-segb")],
        "status": "reviewed",
    },
    {
        "name": "Android Sparse Image",
        "short_name": "sparse img",
        "category": "disk_image",
        "forensic_relevance": (
            "Compressed Android filesystem image used for system partitions. "
            "Must be converted with simg2img before mounting."
        ),
        "platforms": ["Android"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x3a\xff\x26\xed",
                "description": "Android sparse image magic",
            }
        ],
        "extensions": [".img", ".sparse"],
        "links": [("AOSP source", "https://android.googlesource.com/platform/system/core/+/refs/heads/main/libsparse/sparse_format.h")],
        "status": "draft",
    },
    {
        "name": "SQLite Database",
        "short_name": "SQLite",
        "category": "database",
        "forensic_relevance": (
            "Widely used embedded database in browsers, mobile apps, and OS artifacts "
            "such as messages, call logs, browser history, and app data."
        ),
        "platforms": ["Android", "iOS", "macOS", "Windows"],
        "parser_class": "SQLiteParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x53\x51\x4c\x69\x74\x65\x20\x66\x6f\x72\x6d\x61\x74\x20\x33\x00",
                "description": "SQLite database header",
            }
        ],
        "extensions": [".db", ".sqlite", ".sqlite3", ".db3"],
        "links": [("Format spec", "https://www.sqlite.org/fileformat.html")],
        "status": "reviewed",
    },
    {
        "name": "SQLite WAL (Write-Ahead Log)",
        "short_name": "SQLite WAL",
        "category": "database",
        "forensic_relevance": (
            "Write-ahead log companion to a SQLite database. Contains committed "
            "transactions not yet checkpointed into the main .db file. "
            "Opening alongside the .db gives the most current view of the database."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x37\x7f\x06",
                "description": "SQLite WAL magic",
            }
        ],
        "extensions": [".db-wal", ".sqlite-wal", ".sqlite3-wal", ".db3-wal"],
        "links": [("Format spec", "https://www.sqlite.org/walformat.html")],
        "status": "reviewed",
    },
    {
        "name": "TAR Archive",
        "short_name": "TAR",
        "category": "archive",
        "forensic_relevance": (
            "TODO"
        ),
        "platforms": ["Android", "Linux"],
        "parser_class": None,
        "magic": [
            {
                "offset": 257,
                "value": b"\x75\x73\x74\x61\x72",
                "description": "POSIX TAR indicator at offset 257",
            }
        ],
        "extensions": [".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz"],
        "links": [("Format spec", "https://www.gnu.org/software/tar/manual/html_node/Standard.html")],
        "status": "draft",
    },
    {
        "name": "Apple Unified Log (tracev3)",
        "short_name": "tracev3",
        "category": "log",
        "forensic_relevance": (
            "System and application logs since iOS 10 / macOS Sierra. "
            "Rich timeline of app launches, crashes, network events, and user activity."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x30\x74\x72\x33",
                "description": "tracev3 magic",
            }
        ],
        "extensions": [".tracev3"],
        "links": [],
        "status": "draft",
    },
    {
        "name": "XML Document",
        "short_name": "XML",
        "category": "configuration",
        "forensic_relevance": (
            "Configuration files, Android manifests, iOS backup manifests, "
            "app data exports, and structured log formats."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "XmlParser",
        "magic": [],
        "extensions": [".xml", ".xhtml", ".svg", ".kml"],
        "links": [("Format spec", "https://www.w3.org/TR/xml/")],
        "status": "reviewed",
    },
    {
        "name": "ZIP Archive",
        "short_name": "ZIP",
        "category": "archive",
        "forensic_relevance": (
            "General-purpose archive. iOS IPA app packages, Android APKs, "
            "Office documents (DOCX/XLSX), and many other compound formats are ZIPs."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x50\x4b\x03\x04",
                "description": "ZIP local file header signature",
            }
        ],
        "extensions": [".zip", ".ipa", ".apk", ".docx", ".xlsx", ".pptx", ".jar"],
        "links": [("Format spec", "https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT")],
        "status": "draft",
    },
]


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(out_path: Path = _OUT) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    conn = sqlite3.connect(out_path)
    conn.executescript("""
        CREATE TABLE formats (
            id                  INTEGER PRIMARY KEY,
            name                TEXT NOT NULL,
            short_name          TEXT,
            category            TEXT,
            forensic_relevance  TEXT,
            platforms           TEXT,
            parser_class        TEXT
        );
        CREATE TABLE magic_bytes (
            id          INTEGER PRIMARY KEY,
            format_id   INTEGER NOT NULL REFERENCES formats(id),
            offset      INTEGER,
            pattern     BLOB NOT NULL,
            description TEXT
        );
        CREATE TABLE extensions (
            format_id   INTEGER NOT NULL REFERENCES formats(id),
            extension   TEXT NOT NULL
        );
        CREATE TABLE links (
            id          INTEGER PRIMARY KEY,
            format_id   INTEGER NOT NULL REFERENCES formats(id),
            label       TEXT NOT NULL,
            url         TEXT NOT NULL
        );
        CREATE INDEX idx_magic ON magic_bytes(pattern);
        CREATE INDEX idx_ext   ON extensions(extension);
        CREATE INDEX idx_links ON links(format_id);
    """)

    reviewed = [f for f in FORMATS if f.get("status") == "reviewed"]
    draft = [f for f in FORMATS if f.get("status") != "reviewed"]
    if draft:
        print(f"Skipping {len(draft)} draft format(s): {', '.join(f['name'] for f in draft)}")

    for fmt in reviewed:
        platforms = fmt.get("platforms", [])
        if isinstance(platforms, list):
            platforms_str = ",".join(platforms)
        else:
            platforms_str = platforms

        cur = conn.execute(
            "INSERT INTO formats (name, short_name, category, forensic_relevance, "
            "platforms, parser_class) VALUES (?,?,?,?,?,?)",
            (
                fmt["name"],
                fmt.get("short_name", ""),
                fmt.get("category", ""),
                fmt.get("forensic_relevance", ""),
                platforms_str,
                fmt.get("parser_class"),
            ),
        )
        fid = cur.lastrowid
        for m in fmt.get("magic", []):
            conn.execute(
                "INSERT INTO magic_bytes (format_id, offset, pattern, description) VALUES (?,?,?,?)",
                (fid, m.get("offset"), m["value"], m.get("description", "")),
            )
        for ext in fmt.get("extensions", []):
            conn.execute(
                "INSERT INTO extensions (format_id, extension) VALUES (?,?)",
                (fid, ext.lower()),
            )
        for label, url in fmt.get("links", []):
            conn.execute(
                "INSERT INTO links (format_id, label, url) VALUES (?,?,?)",
                (fid, label, url),
            )

    conn.commit()
    conn.close()
    print(f"Built {out_path}  ({len(reviewed)} reviewed formats, {len(FORMATS)} total)")


if __name__ == "__main__":
    build()
