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
            "Android system and app configuration stored as compact binary XML, "
            "introduced in Android 12. Key files include packages.xml (installed apps "
            "and permissions), settings files (global, secure, system), and app backup "
            "manifests. Provides insight into installed software, permission grants, "
            "and system configuration state."
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
                "AOSP source (BinaryXmlSerializer)",
                "https://cs.android.com/android/platform/superproject/main/+/main:frameworks/libs/modules-utils/java/com/android/modules/utils/BinaryXmlSerializer.java",
            ),
            (
                "AOSP abx utility source",
                "https://android.googlesource.com/platform/frameworks/base/+/master/cmds/abx/",
            ),
            (
                "CCL Solutions Group — ABX research",
                "https://www.cclsolutionsgroup.com/post/android-abx-binary-xml",
            ),
            (
                "Android settings forensic analysis (Mattia Epifani)",
                "https://blog.digital-forensics.it/2024/01/analysis-of-android-settings-during.html",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "Android Backup Archive",
        "short_name": "Android backup",
        "category": "archive",
        "forensic_relevance": (
            "Backup created via ADB backup functionality (deprecated since Android 12 / API 31+). "
            "The archive is a TAR stream compressed with Deflate, optionally encrypted with AES-256. "
            "Contains app data, shared storage, and system settings depending on app configuration. "
            "Forensically relevant as a logical acquisition path — but significantly limited: "
            "apps setting allowBackup=false (e.g. banking, messaging) are excluded, "
            "and apps targeting Android 12+ are automatically excluded. "
            "Can reveal installed app data, preferences, and media for apps that permit backup."
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
                "AOSP source (BackupManagerService)",
                "https://android.googlesource.com/platform/frameworks/base/+/refs/heads/jb-dev/services/java/com/android/server/BackupManagerService.java",
            ),
            (
                "Android Backup Extractor (ABE)",
                "https://github.com/nelenkov/android-backup-extractor",
            ),
            (
                "Format internals (Nikolay Elenkov)",
                "https://nelenkov.blogspot.com/2012/06/unpacking-android-backups.html",
            ),
            (
                "ADB backup forensic acquisition (Andrea Fortuna)",
                "https://andreafortuna.org/2017/12/29/forensic-logical-acquisition-of-android-devices-using-adb-backup/",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "Binary Property List",
        "short_name": "bplist",
        "category": "configuration",
        "forensic_relevance": (
            "App preferences, caches, configuration, and iOS/macOS backup structures "
            "such as Manifest.plist and Info.plist. Many bplist files are NSKeyedArchiver "
            "object graphs — recognisable by the '$archiver' key — which can contain "
            "messages, contacts, health records, and other complex app data. "
            "Timestamps use Mac Absolute Time (seconds since 2001-01-01 UTC). "
            "Widely used across all Apple platforms and most third-party iOS/macOS apps."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": "PlistParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x62\x70\x6c\x69\x73\x74",
                "description": "Binary plist magic ('bplist')",
            }
        ],
        "extensions": [".plist"],
        "links": [
            (
                "Apple CoreFoundation source (format spec)",
                "https://opensource.apple.com/source/CF/CF-550/CFBinaryPList.c",
            ),
            (
                "Apple developer docs (Property Lists)",
                "https://developer.apple.com/library/archive/documentation/CoreFoundation/Conceptual/CFPropertyLists/",
            ),
            (
                "NSKeyedArchiver plist forensics (Sarah Edwards / mac4n6)",
                "https://www.mac4n6.com/blog/tag/plist",
            ),
            (
                "ccl-bplist Python module (CCL Solutions Group)",
                "https://github.com/cclgroupltd/ccl-bplist",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "CBOR (Concise Binary Object Representation)",
        "short_name": "CBOR",
        "category": "serialization",
        "forensic_relevance": (
            "RFC 8949 binary serialization format increasingly found in mobile and web app data. "
            "Mandatory encoding for WebAuthn/FIDO2 authentication — passkey credential data, "
            "attestation objects, and public key material on iOS, Android, and Windows are "
            "CBOR-encoded. Also used in some messaging app caches and IoT device communication. "
            "No magic bytes — identification relies on file extension or surrounding context. "
            "Structurally similar to JSON but binary; a CBOR decoder is required to recover "
            "readable key/value structures."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": None,
        "magic": [],
        "extensions": [".cbor"],
        "links": [
            (
                "Format spec (RFC 8949)",
                "https://www.rfc-editor.org/rfc/rfc8949.html",
            ),
            (
                "CBOR overview and tools",
                "https://cbor.io/",
            ),
            (
                "COSE (CBOR Object Signing and Encryption, RFC 8152)",
                "https://www.rfc-editor.org/rfc/rfc8152.html",
            ),
            (
                "WebAuthn spec (CBOR usage)",
                "https://www.w3.org/TR/webauthn-2/",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "Realm Database",
        "short_name": "Realm",
        "category": "database",
        "forensic_relevance": (
            "Mobile app local object store used as a SQLite alternative, now marketed "
            "as MongoDB Atlas Device SDK. A single '.realm' file stores all object data "
            "in a B+ tree of fixed-size arrays. Crush extracts the full schema (class/table "
            "names such as 'class_Driver', 'class_Event', 'class_Photo') and decodes both "
            "root references (top_ref[0] / top_ref[1]) that act as a WAL-like journaling "
            "pair — the inactive branch may contain superseded data not yet checkpointed. "
            "Class names reveal which app features were in use and what data categories "
            "are present (users, locations, media, events, etc.). "
            "Some Realm databases are AES-256 encrypted — key material is typically "
            "hardcoded or derivable from the app binary."
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
                "Realm file format internals",
                "https://mongodben.github.io/flutter-sdk-docs/sdk/flutter/realm-database",
            ),
            (
                "Realm Studio (open .realm files)",
                "https://www.mongodb.com/docs/atlas/device-sdks/studio/open-realm-file/",
            ),
            (
                "Realm forensics primer (Alexis Brignoni)",
                "https://abrignoni.blogspot.com/2019/11/realm-database-storage-primer-for.html",
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
                "Deleted data recovery from Realm DB (ScienceDirect)",
                "https://www.sciencedirect.com/science/article/abs/pii/S2666281722000221",
            ),
            (
                "Mobile App Forensics: A Practical Guide (Realm chapter)",
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
            "Compiled Android application bytecode executed by the Android Runtime (ART). "
            "Found as classes.dex (and classes2.dex, classes3.dex in multi-DEX apps) inside "
            "APK packages, which are ZIP archives. Decompilation with tools like jadx or "
            "apktool can recover app logic, hardcoded API keys, credentials, server endpoints, "
            "and encryption keys. Presence of OAT/ODEX companions confirms the app was "
            "installed and executed on the device."
        ),
        "platforms": ["Android"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x64\x65\x78\x0a",
                "description": "DEX magic ('dex\\n')",
            }
        ],
        "extensions": [".dex"],
        "links": [
            (
                "DEX format specification (AOSP)",
                "https://source.android.com/docs/core/runtime/dex-format",
            ),
            (
                "jadx — DEX to Java decompiler",
                "https://github.com/skylot/jadx",
            ),
            (
                "apktool — APK reverse engineering",
                "https://apktool.org/",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "Apple Disk Image (DMG)",
        "short_name": "DMG",
        "category": "disk_image",
        "forensic_relevance": (
            "macOS disk image format used for app distribution, software installers, "
            "and user-created backups. Contains HFS+, APFS, or FAT32 filesystems "
            "requiring mounting or extraction for analysis. Can be AES-128 or AES-256 "
            "encrypted — password required for access. "
            "Identified by a 512-byte 'koly' trailer block at EOF rather than a file header — "
            "standard magic byte detection will fail. "
            "Also used as a native forensic acquisition format for macOS devices (SWGDE). "
            "Commonly found in Downloads folders and as components of Time Machine sparsebundles."
        ),
        "platforms": ["macOS"],
        "parser_class": None,
        "magic": [
            {
                "offset": None,
                "value": b"\x6b\x6f\x6c\x79",
                "description": "DMG 'koly' trailer block at EOF-512 (no file header magic)",
            }
        ],
        "extensions": [".dmg", ".sparseimage", ".sparsebundle"],
        "links": [
            (
                "DMG format reverse-engineered (newosxbook.com)",
                "https://newosxbook.com/DMG.html",
            ),
            (
                "Apple Disk Image (Wikipedia — UDIF structure)",
                "https://en.wikipedia.org/wiki/Apple_Disk_Image",
            ),
            (
                "ForensicsWiki — DMG",
                "https://forensics.wiki/dmg/",
            ),
            (
                "SWGDE Best Practices macOS Forensic Acquisition",
                "https://www.swgde.org/documents/published-complete-listing/23-f-005-swgde-best-practices-apple-macos-forensic-acquisition/",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "ELF Executable",
        "short_name": "ELF",
        "category": "execution",
        "forensic_relevance": (
            "Native executable and shared library format for Android and Linux. "
            "On Android, ELF shared libraries (.so) are bundled inside APK packages "
            "under lib/ and loaded at runtime via JNI — they often contain hardcoded "
            "strings, API endpoints, encryption keys, and security-sensitive logic "
            "not visible in DEX bytecode. Malware authors frequently move sensitive "
            "code into native libraries precisely because ELF is harder to decompile "
            "than DEX. On Linux, ELF binaries reveal installed software and potential "
            "implants. Strings extraction is a fast first step; full analysis requires "
            "a disassembler such as Ghidra or IDA Pro."
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
        "links": [
            (
                "ELF format specification (man page)",
                "https://man7.org/linux/man-pages/man5/elf.5.html",
            ),
            (
                "Ghidra — open source reverse engineering tool (NSA)",
                "https://ghidra-sre.org/",
            ),
            (
                "Reversing Android native libraries (HackTricks)",
                "https://book.hacktricks.xyz/mobile-pentesting/android-app-pentesting/reversing-native-libraries",
            ),
            (
                "ELF shared library injection forensics",
                "https://engineering.backtrace.io/2016-04-14-elf-shared-library-injection-forensics/",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "Windows Event Log (EVTX)",
        "short_name": "EVTX",
        "category": "log",
        "forensic_relevance": (
            "Windows structured event log format used since Vista/Server 2008, "
            "stored under C:\\Windows\\System32\\winevt\\Logs\\. "
            "Key forensic sources: Security.evtx (logons 4624/4625, account changes, "
            "privilege use 4672), System.evtx (service installs, crashes, boot events), "
            "Microsoft-Windows-PowerShell (4103/4104 script block logging), "
            "Microsoft-Windows-Sysmon (process creation, network, file events). "
            "Event ID 1102 (Security log cleared) and 104 (System log cleared) are "
            "significant anti-forensic indicators. "
            "Note: event messages are not stored in the EVTX file itself — they are "
            "resolved via provider DLLs at display time. Copying EVTX files off-system "
            "may result in unresolvable messages without a message database."
        ),
        "platforms": ["Windows"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x45\x6c\x66\x46\x69\x6c\x65\x00",
                "description": "EVTX file signature ('ElfFile')",
            }
        ],
        "extensions": [".evtx"],
        "links": [
            (
                "EVTX format specification (libevtx)",
                "https://github.com/libyal/libevtx/blob/main/documentation/Windows%20XML%20Event%20Log%20(EVTX).asciidoc",
            ),
            (
                "ForensicsWiki — Windows XML Event Log (EVTX)",
                "https://forensics.wiki/windows_xml_event_log_(evtx)/",
            ),
            (
                "Windows Event Log forensics (ElcomSoft)",
                "https://blog.elcomsoft.com/2026/02/forensic-analysis-of-windows-10-and-11-event-logs/",
            ),
            (
                "EVTX and message resolution (Velociraptor docs)",
                "https://docs.velociraptor.app/docs/forensic/event_logs/",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "JPEG Image",
        "short_name": "JPEG",
        "category": "document",
        "forensic_relevance": (
            "Photos and screenshots from device cameras, messaging apps, and downloads. "
            "EXIF metadata can contain GPS coordinates, timestamps, device model, camera "
            "settings, and an embedded thumbnail — the thumbnail may reveal original content "
            "even after the main image was cropped or edited. "
            "EXIF data can be stripped or manipulated, so timestamps should be corroborated "
            "with filesystem metadata and other sources. "
            "Quantization tables in the JPEG structure can identify the software used to "
            "save or re-encode the file. "
            "JPEG is a common steganographic carrier — data can be hidden in DCT coefficients "
            "or appended after the EOI marker. "
            "XMP metadata may additionally record editing history and software chain."
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
            (
                "JPEG format spec (ITU-T T.81)",
                "https://www.itu.int/rec/T-REC-T.81/en",
            ),
            (
                "EXIF spec (CIPA DC-008)",
                "https://www.cipa.jp/e/std/std-sec.html",
            ),
            (
                "Forensically — online JPEG forensics tool",
                "https://29a.ch/photo-forensics/",
            ),
            (
                "JPEG authentication via EXIF and decoding properties (CFSL)",
                "https://www.researchgate.net/publication/329880328_Authentication_of_Digital_Image_using_Exif_Metadata_and_Decoding_Properties",
            ),
            (
                "ExifTool — read/write metadata",
                "https://exiftool.org/",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "PNG Image",
        "short_name": "PNG",
        "category": "document",
        "forensic_relevance": (
            "Lossless image format used for screenshots, app icons, and UI graphics. "
            "Unlike JPEG, PNG uses lossless compression — pixel data is preserved exactly. "
            "Metadata is stored in typed chunks: tEXt/zTXt for plain-text comments, "
            "iTXt for Unicode and XMP data, tIME for last-modification timestamp, "
            "eXIf for EXIF data (PNG 1.6+). "
            "The IEND chunk marks the end of the file — any data appended after IEND "
            "is forensically significant and may indicate steganography or embedded payloads. "
            "LSB steganography in IDAT pixel data is common and detectable with tools like zsteg. "
            "Screenshots typically lack camera EXIF metadata, which can help distinguish them "
            "from camera photos. The iDOT chunk is Apple-specific and undocumented."
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
        "links": [
            (
                "PNG format spec (W3C)",
                "https://www.w3.org/TR/PNG/",
            ),
            (
                "PNG chunk types reference",
                "https://www.dcode.fr/png-chunks",
            ),
            (
                "pngcheck — PNG integrity and chunk inspector",
                "http://www.libpng.org/pub/png/apps/pngcheck.html",
            ),
            (
                "Steganography detection in PNG (IEND, LSB, chunks)",
                "https://klaroskope.com/learn/steganography-detection-techniques",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "GIF Image",
        "short_name": "GIF",
        "category": "document",
        "forensic_relevance": (
            "Palette-based image format supporting animation, used in messaging apps, "
            "browser caches, and social media. Limited to 256 colors per frame — genuine "
            "photos in GIF format are rare and worth scrutinizing. "
            "GIF89a adds animation frames, comment extensions (free-text metadata), "
            "plain text extensions, and application extensions. "
            "The file terminates with a trailer byte (0x3B) — any data appended after "
            "the trailer is forensically significant. "
            "Steganography is possible via LSB encoding in the global color palette, "
            "palette reordering, or data hidden in comment/application extension blocks. "
            "Animated GIFs can hide different content in individual frames."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "ImageParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x47\x49\x46\x38\x37\x61",
                "description": "GIF87a header — static images only",
            },
            {
                "offset": 0,
                "value": b"\x47\x49\x46\x38\x39\x61",
                "description": "GIF89a header — animation, comments, and extensions supported",
            },
        ],
        "extensions": [".gif"],
        "links": [
            (
                "GIF89a format spec",
                "https://www.w3.org/Graphics/GIF/spec-gif89a.txt",
            ),
            (
                "ForensicsWiki — GIF",
                "https://forensics.wiki/gif/",
            ),
            (
                "GIF steganography from first principles",
                "https://dtm.uk/gif-steganography/",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "BMP Image",
        "short_name": "BMP",
        "category": "document",
        "forensic_relevance": (
            "Uncompressed bitmap format common in Windows apps, legacy software, "
            "and some screenshot tools. "
            "The BITMAPFILEHEADER at offset 2 contains the declared file size — "
            "any discrepancy between this value and actual file size indicates "
            "appended data or truncation. BMP has no EOF marker, so trailing data "
            "detection relies entirely on this size field. "
            "Pixel data is stored bottom-up by default — row order matters for carving. "
            "Can use RLE compression for 4-bit and 8-bit images. "
            "Very rare on modern mobile devices — presence in an acquisition may itself "
            "be noteworthy. Widely used in Windows clipboard operations and legacy software."
        ),
        "platforms": ["Windows", "Android"],
        "parser_class": "ImageParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x42\x4d",
                "description": "BMP file header signature ('BM')",
            }
        ],
        "extensions": [".bmp", ".dib"],
        "links": [
            (
                "BMP format spec (Microsoft)",
                "https://learn.microsoft.com/en-us/windows/win32/gdi/bitmap-storage",
            ),
            (
                "BMP format (Wikipedia — comprehensive)",
                "https://en.wikipedia.org/wiki/BMP_file_format",
            ),
            (
                "BMP format (Kaitai Struct — formal spec)",
                "https://formats.kaitai.io/bmp/",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "TIFF Image",
        "short_name": "TIFF",
        "category": "document",
        "forensic_relevance": (
            "Flexible container format for high-quality images, document scans, and "
            "camera RAW derivatives. Supports multiple pages in a single file — "
            "multi-page TIFFs are common for scanned documents and fax transmissions "
            "(CCITT Group 3/4 compression). "
            "Carries extensive EXIF, XMP, IPTC, and GPS metadata in Image File Directories (IFDs). "
            "Two byte-order variants: little-endian ('II', Intel) and big-endian ('MM', Motorola), "
            "each with a different magic sequence. "
            "TIFF is the base container for many RAW camera formats (CR2, NEF, DNG) and "
            "for EXIF metadata embedded in JPEG files. "
            "Digital libraries and forensic archives commonly use TIFF as the preservation format. "
            "SubIFDs can contain embedded thumbnails or alternate image representations."
        ),
        "platforms": ["iOS", "macOS", "Windows"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x49\x49\x2a\x00",
                "description": "TIFF little-endian (Intel byte order, 'II')",
            },
            {
                "offset": 0,
                "value": b"\x4d\x4d\x00\x2a",
                "description": "TIFF big-endian (Motorola byte order, 'MM')",
            },
        ],
        "extensions": [".tif", ".tiff"],
        "links": [
            (
                "TIFF 6.0 specification (Adobe)",
                "https://www.adobe.io/content/dam/udp/en/open/standards/tiff/TIFF6.pdf",
            ),
            (
                "TIFF format overview (Wikipedia)",
                "https://en.wikipedia.org/wiki/TIFF",
            ),
            (
                "TIFF tags reference (Library of Congress)",
                "https://www.loc.gov/preservation/digital/formats/content/tiff_tags.shtml",
            ),
            (
                "ExifTool — TIFF/EXIF metadata read/write",
                "https://exiftool.org/",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "WebP Image",
        "short_name": "WebP",
        "category": "document",
        "forensic_relevance": (
            "Modern image format used by Chrome, Android apps, and messaging platforms "
            "for compressed photos, stickers, and screenshots. "
            "Stored in a RIFF container — 'RIFF' at offset 0, 'WEBP' at offset 8. "
            "Supports lossy (VP8) and lossless (VP8L) compression, animation (ANMF frames), "
            "alpha channel, ICC color profiles, and EXIF/XMP metadata in dedicated chunks. "
            "WhatsApp, Telegram, and Signal use WebP for stickers and image storage. "
            "Android has used WebP for screenshots since Android 11. "
            "The lossless variant preserves pixel data exactly — useful for detecting re-encoding. "
            "Unknown chunks in the RIFF structure may contain application-specific or hidden data."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "ImageParser",
        "magic": [
            {
                "offset": 8,
                "value": b"\x57\x45\x42\x50",
                "description": "WebP signature within RIFF container ('WEBP' at offset 8)",
            }
        ],
        "extensions": [".webp"],
        "links": [
            (
                "WebP container specification (Google)",
                "https://developers.google.com/speed/webp/docs/riff_container",
            ),
            (
                "WebP Image Format (RFC 9649)",
                "https://datatracker.ietf.org/doc/rfc9649/",
            ),
            (
                "WebP metadata handling (exiv2)",
                "https://dev.exiv2.org/projects/exiv2/wiki/The_Metadata_in_WEBP_files",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "HEIC / HEIF Image",
        "short_name": "HEIC/HEIF",
        "category": "document",
        "forensic_relevance": (
            "Default photo format on iOS 11+ and supported by Android since version 8. "
            "HEIF (ISO/IEC 23008-12) is the container; HEVC (H.265) is the default codec — "
            "hence the .heic extension on Apple devices. "
            "A single file can contain multiple images: Burst shots, Live Photos "
            "(still image + video clip), Portrait mode depth maps, and HDR variants. "
            "Live Photo video components may be stored separately as .mov alongside the .heic. "
            "Rich EXIF, XMP, and IPTC metadata per image, including GPS, timestamps, "
            "device model, and lens information. Depth maps from Portrait mode are stored "
            "as auxiliary images with XMP metadata. "
            "When iOS transfers HEIC to Windows/Mac via cable or email, it may silently "
            "convert to JPEG — stripping metadata in the process. "
            "Traditional JPEG-based image authentication algorithms do not apply to HEIC. "
            "iCloud Photo Library syncs HEIC — relevant for cloud artifact correlation."
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
            (
                "Apple HEIF WWDC 2017 session (format internals)",
                "https://developer.apple.com/videos/play/wwdc2017/513/",
            ),
            (
                "HEIF format spec (Nokia)",
                "https://nokiatech.github.io/heif/",
            ),
            (
                "HEIF format overview (Library of Congress)",
                "https://www.loc.gov/preservation/digital/formats/fdd/fdd000525.shtml",
            ),
            (
                "Forensic considerations for HEIF (McKeown & Russell, 2020)",
                "https://www.napier.ac.uk/~/media/worktribe/output-2653821/forensic-considerations-for-the-high-efficiency-image-file-format-heif.pdf",
            ),
            (
                "HEIF forensics — authentication implications (Amped Software)",
                "https://blog.ampedsoftware.com/2017/09/29/heif-image-files-forensics-authentication-apocalypse",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "iOS Crash Report",
        "short_name": "IPS / crash",
        "category": "log",
        "forensic_relevance": (
            "Application and system crash reports generated by iOS and macOS. "
            "Two formats: the newer .ips format (iOS 15+ / macOS 12+, JSON-based with "
            "bug_type field — value 309 indicates a crash report) and the older .crash "
            "format (plain text). "
            "Each report contains: app name, bundle ID and version, iOS/macOS version, "
            "device model, hardware identifier (CrashReporter Key), incident UUID, "
            "precise crash timestamp, exception type and reason, "
            "and thread states with stack traces. "
            "Forensically relevant for: establishing a precise timeline of app crashes, "
            "identifying exploitation attempts or repeated crashes of security-relevant apps, "
            "detecting jailbreak-related crashes, and corroborating user activity. "
            "Stored on-device under /var/mobile/Library/Logs/CrashReporter/ and accessible "
            "via Settings → Privacy → Analytics & Improvements → Analytics Data."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": None,
        "magic": [],
        "extensions": [".ips", ".crash"],
        "links": [
            (
                "Apple developer docs — examining crash report fields",
                "https://developer.apple.com/documentation/xcode/examining-the-fields-in-a-crash-report",
            ),
            (
                "Apple developer docs — interpreting JSON crash report format",
                "https://developer.apple.com/documentation/xcode/interpreting-the-json-format-of-a-crash-report",
            ),
            (
                "iOS crash logs forensics (ArtiFast / forensafe.com)",
                "https://forensafe.com/blogs/AppleCrashLogs.html",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "JSON Document",
        "short_name": "JSON",
        "category": "serialization",
        "forensic_relevance": (
            "Human-readable serialization format used pervasively in mobile and web apps. "
            "Forensically relevant as: app configuration and cached API responses, "
            "browser localStorage/sessionStorage exports, browser bookmarks and preferences "
            "(Chrome Bookmarks file, Firefox logins.json), "
            "chat and social media data exports (WhatsApp, Signal, Twitter/X archive), "
            "location data in GeoJSON format, and structured log files (JSONL/NDJSON). "
            "Many apps store sensitive data in plaintext JSON without encryption — "
            "credentials, tokens, and personal data are frequently found in app data directories. "
            "No magic bytes — identification relies on file extension or content inspection "
            "for the leading '{' or '[' character."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "JsonParser",
        "magic": [],
        "extensions": [".json", ".geojson", ".jsonl", ".ndjson"],
        "links": [
            (
                "JSON format spec (RFC 8259)",
                "https://datatracker.ietf.org/doc/html/rfc8259",
            ),
            (
                "GeoJSON format spec (RFC 7946)",
                "https://datatracker.ietf.org/doc/html/rfc7946",
            ),
            (
                "Browser artifacts — JSON files in forensics (HackTricks)",
                "https://book.hacktricks.wiki/en/generic-methodologies-and-resources/basic-forensic-methodology/specific-software-file-type-tricks/browser-artifacts.html",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "LevelDB Database",
        "short_name": "LevelDB",
        "category": "database",
        "forensic_relevance": (
            "Key-value store used by Chrome/Chromium (IndexedDB, localStorage, sessionStorage), "
            "Electron-based apps (Discord, WhatsApp Desktop, Signal Desktop), "
            "and many Android and iOS apps for caches and app state. "
            "LevelDB is not a single file but a directory containing: "
            "CURRENT and MANIFEST-###### (metadata), "
            ".ldb/.sst files (sorted string tables with key-value data), "
            "and ######.log files (write-ahead log with recent mutations). "
            "All files must be parsed together for a complete view. "
            "Deleted or overwritten records survive in .log files with sequence numbers "
            "and a deleted/live state flag — deleted data is often recoverable. "
            "Values are frequently serialized as Protobuf (Chrome V8 objects) or JSON. "
            "Chrome IndexedDB stores web app state, cached API responses, and "
            "browser localStorage — common sources of social media and messaging artifacts."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "LeveldbParser",
        "magic": [],
        "extensions": [".ldb", ".log"],
        "links": [
            (
                "LevelDB format specification (Google)",
                "https://github.com/google/leveldb/blob/main/doc/impl.md",
            ),
            (
                "LevelDB forensics primer — Chrome, Electron and LevelDB (CCL)",
                "https://www.cclsolutionsgroup.com/post/hang-on-thats-not-sqlite-chrome-electron-and-leveldb",
            ),
            (
                "IndexedDB on Chromium — deep dive (CCL)",
                "https://www.cclsolutionsgroup.com/post/indexeddb-on-chromium",
            ),
            (
                "Chrome Session/Local Storage in LevelDB (CCL)",
                "https://www.cclsolutionsgroup.com/post/chromium-session-storage-and-local-storage",
            ),
            (
                "LevelDB forensics — memory and deleted data analysis (ScienceDirect)",
                "https://www.sciencedirect.com/science/article/pii/S2666281724001331",
            ),
            (
                "ForensicsWiki — LevelDB format",
                "https://forensics.wiki/leveldb_format/",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "Apple Unified Log Archive (logarchive)",
        "short_name": "logarchive",
        "category": "log",
        "forensic_relevance": (
            "Packaged Apple Unified Log bundle containing tracev3 binary log files, "
            "uuidtext string catalogs, timesync boot-anchor records, and a DSC directory. "
            "Produced by 'log collect' on macOS/iOS or assembled from a full iOS filesystem "
            "acquisition (/private/var/db/diagnostics/ + /private/var/db/uuidtext/ siblings). "
            "Provides a complete, timestamp-anchored log timeline with resolved process names, "
            "subsystems, and categories across typically 28-30 days of device activity. "
            "Key forensic artifacts: app launches and terminations, lock/unlock and screen events, "
            "network connections, Siri activations, biometric authentication attempts, "
            "USB/external media connections, userActionEvent entries (explicit user interactions), "
            "lossEvent entries (log buffer overflow gaps), and crash precursors. "
            "Private message fields may contain data redacted in live-system logs "
            "but preserved in binary acquisitions. "
            "Full string resolution requires uuidtext/, timesync/, and DSC — "
            "without them, message text falls back to raw format-string fragments. "
            "Crush assembles the correct logarchive layout from iOS full-filesystem "
            "acquisitions automatically."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": "UnifiedLogConverter",
        "magic": [],
        "extensions": [".logarchive"],
        "links": [
            (
                "Apple OSLog documentation",
                "https://developer.apple.com/documentation/oslog",
            ),
            (
                "Mandiant macos-UnifiedLogs parser",
                "https://github.com/mandiant/macos-UnifiedLogs",
            ),
            (
                "iOS Unified Logs research (ios-unifiedlogs.com)",
                "https://www.ios-unifiedlogs.com/",
            ),
            (
                "Reviewing macOS Unified Logs — forensic guide (Mandiant/Google)",
                "https://cloud.google.com/blog/topics/threat-intelligence/reviewing-macos-unified-logs/",
            ),
            (
                "Logs Unite! — forensic analysis of Apple Unified Logs (Sarah Edwards)",
                "https://github.com/mac4n6/Presentations/blob/master/Logs%20Unite!%20-%20Forensic%20Analysis%20of%20Apple%20Unified%20Logs/LogsUnite.pdf",
            ),
            (
                "Apple Unified Logging and Activity Tracing formats (libyal)",
                "https://github.com/libyal/dtformats/blob/main/documentation/Apple%20Unified%20Logging%20and%20Activity%20Tracing%20formats.asciidoc",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "LZFSE Compressed Data",
        "short_name": "LZFSE",
        "category": "archive",
        "forensic_relevance": (
            "Apple-proprietary lossless compression algorithm introduced with iOS 9 "
            "and macOS 10.11 (El Capitan). Used in OTA software updates, IPSW firmware "
            "payloads, Dyld Shared Cache (DSC), kernelcache, some system binaries, "
            "and app data. Files must be decompressed before content analysis. "
            "Identified by the 'bvx2' magic (0x62767832). "
            "Apple also uses a simpler variant called LZVN (used for inputs under 4096 bytes "
            "and unconditionally in Mach-O compressed segments). "
            "The open-source lzfse CLI tool (github.com/lzfse/lzfse) can decompress files. "
            "Also used in Apple Archive (.aar) format since macOS Big Sur."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x62\x76\x78\x32",
                "description": "LZFSE magic ('bvx2')",
            }
        ],
        "extensions": [],
        "links": [
            (
                "LZFSE reference implementation (Apple/GitHub)",
                "https://github.com/lzfse/lzfse",
            ),
            (
                "Apple developer docs — Compression framework",
                "https://developer.apple.com/documentation/compression/algorithm/lzfse",
            ),
            (
                "LZFSE overview (Wikipedia)",
                "https://en.wikipedia.org/wiki/LZFSE",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "Mach-O Executable",
        "short_name": "Mach-O",
        "category": "execution",
        "forensic_relevance": (
            "Native executable, library, and object format for iOS and macOS. "
            "App binaries can be analysed for hardcoded strings, URLs, API endpoints, "
            "encryption keys, and embedded credentials. "
            "Entitlements (XML embedded via LC_CODE_SIGNATURE) define app sandbox "
            "capabilities and permissions — relevant for identifying over-privileged apps "
            "or jailbreak bypass attempts. "
            "Code signatures link the binary to a developer identity and detect tampering. "
            "Fat/Universal Binaries contain multiple architecture slices (e.g. arm64 + x86_64) "
            "in a single file, preceded by a fat_header with magic 0xCAFEBABE. "
            "Analysis tools: jtool2, otool, Ghidra, IDA Pro, class-dump, lipo, strings."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\xcf\xfa\xed\xfe",
                "description": "Mach-O 64-bit little-endian (arm64, x86_64) — most common on modern devices",
            },
            {
                "offset": 0,
                "value": b"\xce\xfa\xed\xfe",
                "description": "Mach-O 32-bit little-endian",
            },
            {
                "offset": 0,
                "value": b"\xca\xfe\xba\xbe",
                "description": "Fat/Universal Binary — contains multiple architecture slices",
            },
            {
                "offset": 0,
                "value": b"\xfe\xed\xfa\xcf",
                "description": "Mach-O 64-bit big-endian",
            },
        ],
        "extensions": ["", ".dylib", ".framework", ".o"],
        "links": [
            (
                "Apple developer docs — Mach-O format reference",
                "https://developer.apple.com/library/archive/documentation/Performance/Conceptual/CodeFootprint/Articles/MachOOverview.html",
            ),
            (
                "Mach-O ABI reference (GitHub mirror)",
                "https://github.com/aidansteele/osx-abi-macho-file-format-reference",
            ),
            (
                "Mach-O format overview (Wikipedia)",
                "https://en.wikipedia.org/wiki/Mach-O",
            ),
            (
                "Mach-O forensics — code signing and entitlements (Hexiosec)",
                "https://hexiosec.com/blog/macho-files/",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "MP4 Video",
        "short_name": "MP4",
        "category": "document",
        "forensic_relevance": (
            "Versatile ISOBMFF container format (ISO/IEC 14496-12) for video recordings, "
            "screen captures, and downloaded media. "
            "The ftyp box at offset 4 identifies the specific brand (mp42, isom, M4V, etc.). "
            "The mvhd (Movie Header) box contains creation and modification timestamps "
            "in QuickTime epoch (seconds since 1904-01-01 UTC — not Unix epoch). "
            "The udta (User Data) box may contain device make/model, recording software, "
            "and GPS coordinates (e.g. from GoPro, DJI, dashcams, smartphones). "
            "Metadata changes when a video is re-encoded or edited — "
            "altered mvhd timestamps and missing udta boxes are indicators of processing. "
            "Screen recordings from iOS and Android are commonly stored as MP4. "
            "ExifTool and MediaInfo are standard tools for metadata extraction."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 4,
                "value": b"\x66\x74\x79\x70",
                "description": "ISOBMFF ftyp box at offset 4",
            }
        ],
        "extensions": [".mp4", ".m4v"],
        "links": [
            (
                "ISOBMFF format overview (Wikipedia)",
                "https://en.wikipedia.org/wiki/ISO_base_media_file_format",
            ),
            (
                "MP4 file format spec (ISO/IEC 14496-14)",
                "https://www.iso.org/standard/79110.html",
            ),
            (
                "MP4 authentication via container structure (ResearchGate)",
                "https://www.researchgate.net/publication/351224338_AUTHENTICATION_OF_DIGITAL_MP4_VIDEO_RECORDINGS_USING_FILE_CONTAINERS_AND_METADATA_PROPERTIES",
            ),
            (
                "MPEG-4 file structure forensics — mvhd and metadata (UC Denver)",
                "https://www.ucdenver.edu/docs/librariesprovider27/ncmf-docs/theses/hall_thesis_fall2015.pdf",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "MOV Video (QuickTime)",
        "short_name": "MOV",
        "category": "document",
        "forensic_relevance": (
            "Apple's native video container format based on ISOBMFF/QuickTime. "
            "iOS camera recordings — including the video component of Live Photos — "
            "are stored as .mov files. macOS screen recordings also use MOV. "
            "Identified by ISOBMFF ftyp box at offset 4 with 'qt  ' brand at offset 8. "
            "Timestamps use the QuickTime epoch (seconds since 1904-01-01 UTC). "
            "GPS coordinates are stored as Apple-specific metadata keys "
            "('com.apple.quicktime.location.ISO6709') in the udta/Keys box — "
            "extractable with ExifTool or ffprobe. "
            "Device make/model, software version, and creation date are commonly present. "
            "Files processed by QuickTime Player, iMovie, or Final Cut Pro will show "
            "altered timestamps and may lack original device metadata — "
            "a key indicator of post-processing."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 4,
                "value": b"\x66\x74\x79\x70",
                "description": "ISOBMFF ftyp box at offset 4",
            },
            {
                "offset": 8,
                "value": b"\x71\x74\x20\x20",
                "description": "QuickTime brand identifier ('qt  ') at offset 8",
            },
        ],
        "extensions": [".mov"],
        "links": [
            (
                "QuickTime file format spec (Apple)",
                "https://developer.apple.com/library/archive/documentation/QuickTime/QTFF/QTFFPreface/qtffPreface.html",
            ),
            (
                "Apple developer docs — QuickTime metadata atoms",
                "https://developer.apple.com/documentation/quicktime-file-format/metadata_atoms_and_types",
            ),
            (
                "Apple developer docs — location metadata in MOV",
                "https://developer.apple.com/documentation/quicktime-file-format/location_metadata",
            ),
            (
                "Geolocation metadata in iOS MOV files (practical guide)",
                "https://blog.addpipe.com/geolocation-metadata-ios-android-video-files/",
            ),
            (
                "ExifTool QuickTime tags reference",
                "https://exiftool.org/TagNames/QuickTime.html",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "AVI Video",
        "short_name": "AVI",
        "category": "document",
        "forensic_relevance": (
            "Legacy RIFF-based video container format common in older Windows recordings, "
            "CCTV/DVR systems, dashcams, and surveillance cameras. "
            "RIFF header at offset 0, 'AVI ' identifier at offset 8. "
            "AVI has no native creation timestamp fields — recording time must be inferred "
            "from filesystem metadata or INFO chunk strings. "
            "INFO chunks (ICRT, IDIT, ICRD, ISFT, INAM) may contain creation date/time, "
            "recording software, device info, and comments — content varies by device. "
            "The stream header (strh) fourcc identifies the codec, which can fingerprint "
            "the recording device or software. "
            "Files edited with AVIDemux, VirtualDub, or FFmpeg leave tool-specific "
            "JUNK chunks — a forensic indicator of post-processing. "
            "Standard RIFF is limited to ~4GB — larger files require OpenDML "
            "extension (AVI 2.0)."
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
                "description": "AVI subtype identifier ('AVI ') at offset 8",
            },
        ],
        "extensions": [".avi"],
        "links": [
            (
                "AVI RIFF file reference (Microsoft)",
                "https://learn.microsoft.com/en-us/windows/win32/directshow/avi-riff-file-reference",
            ),
            (
                "AVI format overview (Wikipedia)",
                "https://en.wikipedia.org/wiki/Audio_Video_Interleave",
            ),
            (
                "Forensic analysis of video file formats — AVI and MP4 (DFRWS 2014)",
                "https://dfrws.org/wp-content/uploads/2019/06/2014_EU_paper-forensic_analysis_of_video_file_formats.pdf",
            ),
            (
                "RIFF INFO tags in AVI (ExifTool)",
                "https://exiftool.org/TagNames/RIFF.html",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "MKV Video (Matroska)",
        "short_name": "MKV",
        "category": "document",
        "forensic_relevance": (
            "Open EBML-based container format for HD video, commonly found in "
            "downloaded media, media server libraries (Plex, Jellyfin), and screen recordings. "
            "Supports chapters, subtitles, attachments, and multiple audio/video tracks. "
            "The Segment Info element contains key forensic metadata: "
            "DateUTC (nanoseconds since 2001-01-01 UTC — the muxing timestamp), "
            "Title, MuxingApp (library used), and WritingApp (application used). "
            "WritingApp and MuxingApp are mandatory fields — they identify the software "
            "that created or remuxed the file (e.g. HandBrake, FFmpeg, MakeMKV, mkvmerge) "
            "and are strong indicators of post-processing. "
            "Shares the EBML magic (0x1A 0x45 0xDF 0xA3) with WebM — "
            "distinguished by DocType 'matroska' vs 'webm' in the EBML header."
        ),
        "platforms": ["Android", "Windows", "Linux"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x1a\x45\xdf\xa3",
                "description": "EBML header (Matroska/WebM) — DocType 'matroska' identifies MKV",
            }
        ],
        "extensions": [".mkv"],
        "links": [
            (
                "Matroska format specification (RFC 9559)",
                "https://datatracker.ietf.org/doc/rfc9559/",
            ),
            (
                "Matroska technical basics",
                "https://www.matroska.org/technical/basics.html",
            ),
            (
                "Matroska element reference",
                "https://www.matroska.org/technical/elements.html",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "WebM Video",
        "short_name": "WebM",
        "category": "document",
        "forensic_relevance": (
            "Web-optimised video container based on a restricted subset of Matroska/EBML. "
            "Used by browsers (Chrome, Firefox, Edge), WebRTC recordings, "
            "YouTube downloads, and some Android apps. "
            "Shares the EBML magic (0x1A 0x45 0xDF 0xA3) with MKV — "
            "distinguished by DocType 'webm' in the EBML header. "
            "Restricted to VP8, VP9, or AV1 video with Vorbis or Opus audio only. "
            "Same Segment Info metadata as MKV: DateUTC (nanoseconds since 2001-01-01 UTC), "
            "WritingApp and MuxingApp identify the creation software. "
            "Browser-cached WebM segments from streaming services may contain "
            "partial content rather than complete videos. "
            "WebRTC recordings from browser video calls are commonly stored as WebM."
        ),
        "platforms": ["Android", "Windows", "Linux"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 0,
                "value": b"\x1a\x45\xdf\xa3",
                "description": "EBML header (Matroska/WebM) — DocType 'webm' identifies WebM",
            }
        ],
        "extensions": [".webm"],
        "links": [
            (
                "WebM container guidelines (WebM Project)",
                "https://www.webmproject.org/docs/container/",
            ),
            (
                "WebM overview (Wikipedia)",
                "https://en.wikipedia.org/wiki/WebM",
            ),
            (
                "Matroska format spec (RFC 9559) — WebM base format",
                "https://datatracker.ietf.org/doc/rfc9559/",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "3GP / 3G2 Video",
        "short_name": "3GP",
        "category": "document",
        "forensic_relevance": (
            "Mobile video container format based on ISOBMFF, defined by 3GPP (3GP) "
            "and 3GPP2 (3G2) for 3G mobile networks. "
            "3GP targets GSM/UMTS networks; 3G2 is the CDMA2000 variant with lower "
            "bandwidth usage. Both are required formats for MMS and IMS multimedia services. "
            "Shares the ISOBMFF box structure with MP4 — same mvhd timestamps "
            "(QuickTime epoch, seconds since 1904-01-01 UTC) and udta metadata. "
            "Typical video codecs: H.263, H.264; audio: AMR-NB, AAC. "
            "Typically low resolution (QCIF 176x144 to CIF 352x288) and bitrate, "
            "optimised for 2G/3G transmission. "
            "Found in older acquisitions, MMS message attachments, voice call recordings, "
            "and legacy Android/iOS camera recordings from pre-2012 devices. "
            "Some devices stored 3GP files with an .mp4 extension."
        ),
        "platforms": ["Android", "iOS"],
        "parser_class": "MediaParser",
        "magic": [
            {
                "offset": 4,
                "value": b"\x66\x74\x79\x70",
                "description": "ISOBMFF ftyp box at offset 4",
            }
        ],
        "extensions": [".3gp", ".3g2"],
        "links": [
            (
                "3GP format specification (3GPP TS 26.244)",
                "https://www.3gpp.org/ftp/Specs/archive/26_series/26.244/",
            ),
            (
                "3GP and 3G2 overview (Wikipedia)",
                "https://en.wikipedia.org/wiki/3GP_and_3G2",
            ),
            (
                "Forensic analysis of mobile video formats (DFRWS 2014)",
                "https://dfrws.org/wp-content/uploads/2019/06/2014_EU_paper-forensic_analysis_of_video_file_formats.pdf",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "MP3 Audio",
        "short_name": "MP3",
        "category": "document",
        "forensic_relevance": (
            "Ubiquitous lossy audio format for music, voice memos, voicemails, "
            "and messaging app voice messages. "
            "ID3v2 tags (at file start, 'ID3' magic) can embed title, artist, album, "
            "year, comments, cover art, lyrics, URLs, and custom frames — "
            "some apps embed GPS coordinates or device info in custom ID3 frames. "
            "ID3v1 tags (last 128 bytes, 'TAG' marker) store basic metadata. "
            "VBR files often contain a Xing/LAME tag in the first MPEG frame — "
            "this encodes the encoding software (e.g. 'LAME 3.99') and settings, "
            "useful for source attribution and detecting re-encoding. "
            "Bitrate and sample rate can help fingerprint the recording device or app. "
            "No native timestamp — recording time must be inferred from ID3 tags "
            "or filesystem metadata."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x49\x44\x33",
                "description": "ID3 tag header (MP3 with ID3v2 metadata)",
            },
            {
                "offset": 0,
                "value": b"\xff\xfb",
                "description": "MPEG-1 Layer 3 sync word (MP3 without ID3 header)",
            },
        ],
        "extensions": [".mp3"],
        "links": [
            (
                "ID3v2 specification (id3.org)",
                "https://id3.org/id3v2.3.0",
            ),
            (
                "ID3 overview (Wikipedia)",
                "https://en.wikipedia.org/wiki/ID3",
            ),
            (
                "LAME tag specification (encoder attribution)",
                "http://gabriel.mp3-tech.org/mp3infotag.html",
            ),
            (
                "ForensicsWiki — ID3",
                "https://forensics.wiki/id3/",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "WAV Audio",
        "short_name": "WAV",
        "category": "document",
        "forensic_relevance": (
            "Uncompressed PCM audio container based on RIFF, used for voice recordings, "
            "call recordings, dictation devices, bodycams, and professional recorders. "
            "RIFF INFO chunks may contain title, creation date, originator, and software. "
            "The Broadcast Wave Format (BWF) extension adds a 'bext' chunk with: "
            "originator name and reference, origination date and time (UTC, YYYY-MM-DD/HH:MM:SS), "
            "TimeReference (64-bit sample count since midnight — precise recording timestamp), "
            "and a CodingHistory field describing the encoding chain. "
            "No native encryption — audio is directly accessible. "
            "Standard RIFF is limited to ~4GB; larger files use RF64 extension. "
            "ExifTool and BWF MetaEdit extract all RIFF and BWF metadata."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x52\x49\x46\x46",
                "description": "RIFF container header",
            },
            {
                "offset": 8,
                "value": b"\x57\x41\x56\x45",
                "description": "WAVE subtype identifier at offset 8",
            },
        ],
        "extensions": [".wav", ".bwf"],
        "links": [
            (
                "EBU Tech 3285 — Broadcast Wave Format specification",
                "https://tech.ebu.ch/docs/tech/tech3285.pdf",
            ),
            (
                "Broadcast Wave Format overview (Wikipedia)",
                "https://en.wikipedia.org/wiki/Broadcast_Wave_Format",
            ),
            (
                "Library of Congress — BWF format description",
                "https://www.loc.gov/preservation/digital/formats/fdd/fdd000356.shtml",
            ),
            (
                "BWF MetaEdit — open source BWF metadata tool",
                "https://mediaarea.net/BWFMetaEdit",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "M4A Audio",
        "short_name": "M4A",
        "category": "document",
        "forensic_relevance": (
            "ISOBMFF audio-only container (ftyp brand 'M4A ') typically containing "
            "AAC (lossy) or ALAC (lossless) audio. "
            "Used for iTunes/Apple Music purchases and downloads, iOS Voice Memos, "
            "GarageBand exports, and FaceTime audio recordings. "
            "Shares box structure with MP4 — same mvhd timestamps "
            "(QuickTime epoch, seconds since 1904-01-01 UTC). "
            "iOS Voice Memos store recordings as M4A with the writing application "
            "field set to 'com.apple.VoiceMemos' — absence or alteration of this "
            "field is a forgery indicator. "
            "The 'ilst' box contains iTunes-style metadata tags (title, artist, "
            "album, comment, encoded date). "
            "iTunes Store purchases with FairPlay DRM use .m4p extension and "
            "cannot be decoded without authorization. "
            "ALAC variant (Apple Music lossless) is bit-perfect — no lossy artefacts."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": None,
        "magic": [
            {
                "offset": 4,
                "value": b"\x66\x74\x79\x70",
                "description": "ISOBMFF ftyp box at offset 4",
            }
        ],
        "extensions": [".m4a", ".m4p", ".m4b"],
        "links": [
            (
                "MPEG-4 Part 14 — MP4/M4A file format (Wikipedia)",
                "https://en.wikipedia.org/wiki/MP4_file_format",
            ),
            (
                "Forensic authentication of iOS Voice Memo M4A recordings",
                "https://www.researchgate.net/publication/337598372_Forensic_originality_identification_of_iPhone_s_voice_memos",
            ),
            (
                "ExifTool QuickTime tags (M4A metadata fields)",
                "https://exiftool.org/TagNames/QuickTime.html",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "AAC Audio",
        "short_name": "AAC",
        "category": "document",
        "forensic_relevance": (
            "Advanced Audio Coding — the dominant lossy audio codec on iOS and Android. "
            "AAC exists in multiple container forms requiring different analysis: "
            "(1) Raw ADTS-framed AAC (.aac) — sync word 0xFFF1 or 0xFFF9, "
            "self-synchronizing frames, minimal metadata, no embedded timestamps; "
            "common in Android voice recorder apps and streaming buffers. "
            "(2) ISOBMFF/M4A container — see M4A entry; most common on iOS. "
            "(3) ADIF (Audio Data Interchange Format) — rare, single header. "
            "Raw ADTS files abruptly stopped (e.g. by crash or battery removal) "
            "remain readable without finalization — unlike MPEG-4 which requires "
            "a complete moov box. "
            "Recording time must be inferred from filesystem timestamps or "
            "container metadata; ADTS carries no embedded timestamps. "
            "Bitrate and sampling rate can help fingerprint the recording device or app."
        ),
        "platforms": ["iOS", "macOS", "Android", "Windows"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\xff\xf1",
                "description": "ADTS AAC sync word — MPEG-4 AAC, no CRC",
            },
            {
                "offset": 0,
                "value": b"\xff\xf9",
                "description": "ADTS AAC sync word — MPEG-2 AAC, no CRC",
            },
        ],
        "extensions": [".aac"],
        "links": [
            (
                "Advanced Audio Coding overview (Wikipedia)",
                "https://en.wikipedia.org/wiki/Advanced_Audio_Coding",
            ),
            (
                "ADTS format internals (MultimediaWiki)",
                "https://wiki.multimedia.cx/index.php/ADTS",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "FLAC Audio",
        "short_name": "FLAC",
        "category": "document",
        "forensic_relevance": (
            "Free Lossless Audio Codec — bit-perfect audio with native metadata support. "
            "Used for music archiving, high-quality recordings, and some Android devices. "
            "FLAC metadata blocks: STREAMINFO (sample rate, bit depth, channel count, "
            "and MD5 signature of the raw audio — useful for integrity verification), "
            "VORBIS_COMMENT (free-form key-value tags: title, artist, album, date, "
            "encoder, and any custom fields), PICTURE (embedded cover art), "
            "SEEKTABLE, and APPLICATION (vendor-specific data). "
            "The vendor string in VORBIS_COMMENT identifies the encoding library "
            "and version (e.g. 'reference libFLAC 1.3.0') — useful for source attribution. "
            "No native recording timestamp — inferred from filesystem metadata or "
            "VORBIS_COMMENT DATE field. "
            "Identified by 'fLaC' magic (0x664C6143) at offset 0."
        ),
        "platforms": ["Android", "Windows", "Linux"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x66\x4c\x61\x43",
                "description": "FLAC stream marker ('fLaC')",
            }
        ],
        "extensions": [".flac"],
        "links": [
            (
                "FLAC format overview (Xiph.org)",
                "https://xiph.org/flac/documentation_format_overview.html",
            ),
            (
                "FLAC format specification (IETF RFC / Xiph)",
                "https://xiph.org/flac/format.html",
            ),
            (
                "FLAC overview (Wikipedia)",
                "https://en.wikipedia.org/wiki/FLAC",
            ),
            (
                "metaflac — FLAC metadata command-line tool",
                "https://xiph.org/flac/documentation_tools_metaflac.html",
            ),
        ],
        "status": "reviewed",
    },
    {
        "name": "OGG Audio",
        "short_name": "OGG",
        "category": "document",
        "forensic_relevance": (
            "Open bitstream container supporting multiple codecs — forensically "
            "encountered as Ogg Vorbis (music, games), Ogg Opus (voice messages), "
            "and Ogg FLAC (lossless audio). "
            "All OGG streams begin with the OggS capture pattern (0x4F676753). "
            "Ogg Opus is the dominant format for voice messages in modern messaging apps: "
            "WhatsApp stores voice notes as .opus (PTT-YYYYMMDD-WANNNN.opus — "
            "timestamp encoded in filename), Telegram stores as .ogg, "
            "both using Opus codec at 16-32 kbps. "
            "Vorbis comment metadata (same key-value format as FLAC) may contain "
            "title, artist, date, encoder, and custom fields. "
            "No native embedded timestamps — recording time inferred from filesystem "
            "metadata or messaging app databases."
        ),
        "platforms": ["Android", "iOS", "Windows", "Linux"],
        "parser_class": None,
        "magic": [
            {
                "offset": 0,
                "value": b"\x4f\x67\x67\x53",
                "description": "OGG capture pattern ('OggS')",
            }
        ],
        "extensions": [".ogg", ".oga", ".opus"],
        "links": [
            (
                "OGG format overview (Xiph.org)",
                "https://xiph.org/ogg/",
            ),
            (
                "Opus codec specification (RFC 6716)",
                "https://datatracker.ietf.org/doc/html/rfc6716",
            ),
            (
                "Ogg Vorbis comment format",
                "https://xiph.org/vorbis/doc/v-comment.html",
            ),
        ],
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
            "Binary log file used by Apple's Unified Logging system since iOS 10 / macOS Sierra. "
            "Replaces ASL and syslog as the primary system log store on all modern Apple platforms. "
            "Each file covers one boot session and records subsystem, category, process, PID, "
            "thread ID, activity ID, log level, and the event message with nanosecond timestamps. "
            "Key forensic value: app launches and terminations, network connections, "
            "lock/unlock and screen events, Siri activations, crash precursors, "
            "userActionEvent entries (explicit user interactions), lossEvent entries "
            "(indicates gaps in the log due to buffer overflow), and signpost intervals "
            "(performance markers that reveal feature usage). "
            "Private message_entries fields may contain data redacted in live-system logs "
            "but preserved in the binary acquisition. "
            "Full string resolution requires the uuidtext/ catalog and DSC (Dyld Shared Cache); "
            "without them message text falls back to raw format-string fragments."
        ),
        "platforms": ["iOS", "macOS"],
        "parser_class": "UnifiedLogConverter",
        "magic": [
            {
                "offset": 0,
                "value": b"\x30\x74\x72\x33",
                "description": "tracev3 header magic ('0tr3')",
            }
        ],
        "extensions": [".tracev3"],
        "links": [
            ("Apple OSLog documentation", "https://developer.apple.com/documentation/oslog"),
            ("Mandiant macos-UnifiedLogs (converter)", "https://github.com/mandiant/macos-UnifiedLogs"),
            ("iOS Unified Logs research", "https://www.ios-unifiedlogs.com/"),
            ("Sarah Edward's research (mac4n6)", "https://www.mac4n6.com/blog/2016/11/13/new-macos-sierra-log-format-and-how-to-access-it"),
        ],
        "status": "reviewed",
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
