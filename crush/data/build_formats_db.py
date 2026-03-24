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

_OUT = Path(__file__).parent / "formats.db"

# ---------------------------------------------------------------------------
# Format definitions
# Each entry:
#   name            Full human-readable name
#   short_name      Abbreviation shown in UI
#   category        plist | database | image | media | archive | log |
#                   serialization | crypto | executable | other
#   forensic_relevance  What an investigator would find here
#   platforms       Comma-separated: iOS, macOS, Android, Windows, Cross-platform
#   parser_class    Class name in crush/parsers/ that handles this, or None
#   magic           List of (offset, bytes) tuples — all must match
#   extensions      List of lowercase extensions including the dot
#   links           List of (label, url) tuples — reference links
# ---------------------------------------------------------------------------

FORMATS: list[dict] = [
    # -----------------------------------------------------------------------
    # Supported formats
    # -----------------------------------------------------------------------
    {
        "name": "SQLite Database",
        "short_name": "SQLite",
        "category": "database",
        "forensic_relevance": (
            "One of the Core storages. Contains messages, call logs, "
            "browser history, contacts, location data, app state, and more."
        ),
        "platforms": "iOS,macOS,Android,Windows",
        "parser_class": "SQLiteParser",
        "magic": [(0, b"SQLite format 3\x00")],
        "extensions": [".db", ".sqlite", ".sqlite3", ".db3"],
        "links": [("Format spec", "https://www.sqlite.org/fileformat.html")],
    },
    {
        "name": "Apple Binary Property List",
        "short_name": "bplist",
        "category": "plist",
        "forensic_relevance": (
            "App preferences, caches, configuration, and iOS backup structures. "
            "NSKeyedArchiver objects are also stored as binary plists."
        ),
        "platforms": "iOS,macOS",
        "parser_class": "PlistParser",
        "magic": [(0, b"bplist")],
        "extensions": [".plist"],
        "links": [("Developer docs", "https://developer.apple.com/library/archive/documentation/CoreFoundation/Conceptual/CFPropertyLists/")],
    },
    {
        "name": "Apple XML Property List",
        "short_name": "plist (XML)",
        "category": "plist",
        "forensic_relevance": (
            "Human-readable version of binary plists. Used for app preferences, "
            "configuration files, and Info.plist manifests."
        ),
        "platforms": "iOS,macOS",
        "parser_class": "PlistParser",
        "magic": [],
        "extensions": [".plist"],
        "links": [("Developer docs", "https://developer.apple.com/library/archive/documentation/CoreFoundation/Conceptual/CFPropertyLists/")],
    },
    {
        "name": "XML Document",
        "short_name": "XML",
        "category": "other",
        "forensic_relevance": (
            "Configuration files, Android manifests, iOS backup manifests, "
            "app data exports, and structured log formats."
        ),
        "platforms": "iOS,macOS,Android,Cross-platform",
        "parser_class": "XmlParser",
        "magic": [],
        "extensions": [".xml", ".xhtml", ".svg", ".kml"],
        "links": [("Format spec", "https://www.w3.org/TR/xml/")],
    },
    {
        "name": "Android Binary XML (ABX)",
        "short_name": "ABX",
        "category": "other",
        "forensic_relevance": (
            "Android system and app settings stored as compact binary XML. "
            "Found in /data/system/ and app data directories."
        ),
        "platforms": "Android",
        "parser_class": "AbxParser",
        "magic": [(0, b"ABX\x00")],
        "extensions": [".xml", ".abx"],
        "links": [("AOSP source", "https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/core/java/com/android/internal/util/BinaryXmlSerializer.java")],
    },
    {
        "name": "Apple SEGB (Biome store)",
        "short_name": "SEGB",
        "category": "log",
        "forensic_relevance": (
            "Apple Biome framework data stores. Contains app usage, screen time, "
            "location, health, and Siri interaction history."
        ),
        "platforms": "iOS,macOS",
        "parser_class": "SegbParser",
        "magic": [(0, b"SEGB")],
        "extensions": [".segb", ".segb1", ".segb2", ".biome"],
        "links": [("Source code", "https://github.com/cclgroupltd/ccl-segb")],
    },
    {
        "name": "LevelDB Database",
        "short_name": "LevelDB",
        "category": "database",
        "forensic_relevance": (
            "Key-value store used by Chrome, browsers, and many Android/iOS apps "
            "for caches, IndexedDB, and app state."
        ),
        "platforms": "iOS,macOS,Android,Cross-platform",
        "parser_class": "LeveldbParser",
        "magic": [],
        "extensions": [".ldb", ".log"],
        "links": [("Format spec", "https://github.com/google/leveldb/blob/main/doc/impl.md")],
    },
    {
        "name": "Image (JPEG / PNG / GIF / WEBP / HEIC)",
        "short_name": "Image",
        "category": "image",
        "forensic_relevance": (
            "Photos, screenshots, thumbnails, and app assets. JPEG/HEIC files "
            "from iOS cameras contain GPS, timestamp, and device EXIF metadata."
        ),
        "platforms": "iOS,macOS,Android,Cross-platform",
        "parser_class": "ImageParser",
        "magic": [
            (0, b"\xff\xd8\xff"),
            (0, b"\x89PNG\r\n\x1a\n"),
        ],
        "extensions": [
            ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
            ".tiff", ".tif", ".heic", ".heif",
        ],
        "links": [("Format spec", "https://exif.org/Exif2-2.PDF")],
    },
    {
        "name": "Media (MP4 / MOV / MP3 / AAC)",
        "short_name": "Media",
        "category": "media",
        "forensic_relevance": (
            "Audio and video recordings, voicemails, and screen recordings. "
            "MP4/MOV containers may contain metadata and GPS tracks."
        ),
        "platforms": "iOS,macOS,Android,Cross-platform",
        "parser_class": "MediaParser",
        "magic": [],
        "extensions": [
            ".mp4", ".mov", ".avi", ".mkv", ".m4v",
            ".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus",
        ],
        "links": [("Format spec", "https://wiki.multimedia.cx/index.php/MPEG-4")],
    },
    {
        "name": "JSON Document",
        "short_name": "JSON",
        "category": "other",
        "forensic_relevance": (
            "App configuration, API responses cached on device, "
            "browser storage, and exported data from many modern apps."
        ),
        "platforms": "iOS,macOS,Android,Cross-platform",
        "parser_class": "JsonParser",
        "magic": [],
        "extensions": [".json", ".geojson", ".jsonl", ".ndjson"],
        "links": [("Format spec", "https://datatracker.ietf.org/doc/html/rfc8259")],
    },
    {
        "name": "PDF Document",
        "short_name": "PDF",
        "category": "other",
        "forensic_relevance": (
            "Documents, receipts, tickets, and exported reports stored in apps "
            "or transmitted via messaging. May contain metadata, author, and dates."
        ),
        "platforms": "iOS,macOS,Android,Cross-platform",
        "parser_class": "PDFParser",
        "magic": [(0, b"%PDF")],
        "extensions": [".pdf"],
        "links": [("Format spec", "https://opensource.adobe.com/dc-acrobat-sdk-docs/standards/pdfstandards/pdf/PDF32000_2008.pdf")],
    },

    # -----------------------------------------------------------------------
    # Unsupported formats — identified but not yet parsed
    # -----------------------------------------------------------------------
    {
        "name": "Apple Unified Log (tracev3)",
        "short_name": "tracev3",
        "category": "log",
        "forensic_relevance": (
            "System and application logs since iOS 10 / macOS Sierra. "
            "Rich timeline of app launches, crashes, network events, and user activity."
        ),
        "platforms": "iOS,macOS",
        "parser_class": None,
        "magic": [(0, b"\x30\x74\x72\x33")],
        "extensions": [".tracev3"],
        "links": [("Source code", "https://github.com/mandiant/macos-UnifiedLogs")],
    },
    {
        "name": "Apple Unified Log Archive (logarchive)",
        "short_name": "logarchive",
        "category": "log",
        "forensic_relevance": (
            "Packaged collection of tracev3 log files and UUID maps. "
            "Primary log artifact from sysdiagnose captures."
        ),
        "platforms": "iOS,macOS",
        "parser_class": None,
        "magic": [],
        "extensions": [".logarchive"],
        "links": [("Source code", "https://github.com/mandiant/macos-UnifiedLogs")],
    },
    {
        "name": "iOS Crash Report",
        "short_name": "IPS / crash",
        "category": "log",
        "forensic_relevance": (
            "Application crash reports with stack traces, thread states, "
            "and exception details. Indicate app instability or exploitation attempts."
        ),
        "platforms": "iOS,macOS",
        "parser_class": None,
        "magic": [],
        "extensions": [".ips", ".crash"],
        "links": [("Developer docs", "https://developer.apple.com/documentation/xcode/examining-the-fields-in-a-crash-report")],
    },
    {
        "name": "Apple LZFSE Compressed Data",
        "short_name": "LZFSE",
        "category": "archive",
        "forensic_relevance": (
            "Apple-proprietary compression used in iOS 9+ system files, "
            "OTA updates, and some app data. Must be decompressed before analysis."
        ),
        "platforms": "iOS,macOS",
        "parser_class": None,
        "magic": [(0, b"bvx2")],
        "extensions": [],
        "links": [("Source code", "https://github.com/lzfse/lzfse")],
    },
    {
        "name": "Protocol Buffers (protobuf)",
        "short_name": "protobuf",
        "category": "serialization",
        "forensic_relevance": (
            "Binary serialization format used by Google apps, Chrome, WhatsApp, "
            "Signal, and many others. Requires .proto schema to decode field names."
        ),
        "platforms": "iOS,macOS,Android,Cross-platform",
        "parser_class": None,
        "magic": [],
        "extensions": [".pb", ".proto"],
        "links": [("Format spec", "https://protobuf.dev/programming-guides/encoding/")],
    },
    {
        "name": "Android DEX Bytecode",
        "short_name": "DEX",
        "category": "executable",
        "forensic_relevance": (
            "Compiled Android application code. Can be decompiled to recover "
            "app logic, hardcoded credentials, and API endpoints."
        ),
        "platforms": "Android",
        "parser_class": None,
        "magic": [(0, b"dex\n")],
        "extensions": [".dex"],
        "links": [("AOSP source", "https://source.android.com/docs/core/runtime/dex-format")],
    },
    {
        "name": "Android OAT / ART Compiled Code",
        "short_name": "OAT",
        "category": "executable",
        "forensic_relevance": (
            "ART-compiled versions of DEX files. Presence indicates the app "
            "was installed and executed on the device."
        ),
        "platforms": "Android",
        "parser_class": None,
        "magic": [(0, b"oat\n")],
        "extensions": [".oat", ".odex", ".vdex"],
        "links": [("AOSP source", "https://source.android.com/docs/core/runtime")],
    },
    {
        "name": "Android Sparse Image",
        "short_name": "sparse img",
        "category": "archive",
        "forensic_relevance": (
            "Compressed Android filesystem image used for system partitions. "
            "Must be converted with simg2img before mounting."
        ),
        "platforms": "Android",
        "parser_class": None,
        "magic": [(0, b"\x3a\xff\x26\xed")],
        "extensions": [".img", ".sparse"],
        "links": [("AOSP source", "https://android.googlesource.com/platform/system/core/+/refs/heads/main/libsparse/sparse_format.h")],
    },
    {
        "name": "Android Backup Archive",
        "short_name": "Android backup",
        "category": "archive",
        "forensic_relevance": (
            "Full or partial app data backup created via ADB. Contains app APKs "
            "and data as a compressed TAR wrapped in a custom header."
        ),
        "platforms": "Android",
        "parser_class": None,
        "magic": [(0, b"ANDROID BACKUP\n")],
        "extensions": [".ab"],
        "links": [("Research", "https://nelenkov.blogspot.com/2012/06/unpacking-android-backups.html")],
    },
    {
        "name": "MessagePack",
        "short_name": "msgpack",
        "category": "serialization",
        "forensic_relevance": (
            "Compact binary serialization used by some messaging and social apps "
            "for caching and inter-process communication."
        ),
        "platforms": "iOS,macOS,Android,Cross-platform",
        "parser_class": None,
        "magic": [],
        "extensions": [".msgpack", ".mp"],
        "links": [("Format spec", "https://msgpack.org/index.html")],
    },
    {
        "name": "CBOR (Concise Binary Object Representation)",
        "short_name": "CBOR",
        "category": "serialization",
        "forensic_relevance": (
            "RFC 8949 binary format used in modern APIs and WebAuthn/FIDO2 "
            "credential storage. Increasingly common in security-relevant app data."
        ),
        "platforms": "iOS,macOS,Android,Cross-platform",
        "parser_class": None,
        "magic": [],
        "extensions": [".cbor"],
        "links": [("Format spec", "https://cbor.io/")],
    },
    {
        "name": "Apple Keychain Database",
        "short_name": "keychain-2.db",
        "category": "crypto",
        "forensic_relevance": (
            "iOS system keychain storing passwords, certificates, tokens, "
            "and encryption keys for all apps. Encrypted — extraction requires "
            "the device passcode or a supported extraction method. "
            # REVIEW: verify accessibility conditions and correct extraction context
        ),
        "platforms": "iOS",
        "parser_class": None,
        "magic": [(0, b"SQLite format 3\x00")],
        "extensions": [".db"],
        "links": [("Developer docs", "https://support.apple.com/guide/security/keychain-data-protection-secb0694df1a/web")],
    },
    {
        "name": "Apple Core Data Store",
        "short_name": "Core Data",
        "category": "database",
        "forensic_relevance": (
            "Persistent object store for iOS/macOS apps using Core Data ORM. "
            "Often contains the main application data model."
        ),
        "platforms": "iOS,macOS",
        "parser_class": None,
        "magic": [(0, b"SQLite format 3\x00")],
        "extensions": [".sqlite", ".sqlite3", ".db"],
        "links": [("Developer docs", "https://developer.apple.com/documentation/coredata")],
    },
    {
        "name": "Apple NSKeyedArchiver Object",
        "short_name": "NSKeyedArchiver",
        "category": "plist",
        "forensic_relevance": (
            "Serialised Objective-C object graph stored as a binary plist. "
            "Widely used for app state, pasteboard, and inter-process serialization."
            # REVIEW: verify primary use cases — clipboard/pasteboard distinction
        ),
        "platforms": "iOS,macOS",
        "parser_class": None,
        "magic": [(0, b"bplist")],
        "extensions": [".plist", ".archive", ".data"],
        "links": [("Developer docs", "https://developer.apple.com/documentation/foundation/nskeyedarchiver")],
    },
    {
        "name": "Windows Registry Hive",
        "short_name": "Registry",
        "category": "database",
        "forensic_relevance": (
            "Windows system and user configuration database. Contains installed "
            "software, user activity, network history, and USB device records."
        ),
        "platforms": "Windows",
        "parser_class": None,
        "magic": [(0, b"regf")],
        "extensions": [".dat", ".hiv"],
        "links": [("Format spec", "https://github.com/msuhanov/regf/blob/master/Windows%20registry%20file%20format%20specification.md")],
    },
    {
        "name": "Windows Event Log (EVTX)",
        "short_name": "EVTX",
        "category": "log",
        "forensic_relevance": (
            "Windows structured event logs. Contains security events, logons, "
            "process creation, PowerShell activity, and system errors."
        ),
        "platforms": "Windows",
        "parser_class": None,
        "magic": [(0, b"ElfFile\x00")],
        "extensions": [".evtx"],
        "links": [("Format spec", "https://github.com/libyal/libevtx/blob/main/documentation/Windows%20XML%20Event%20Log%20(EVTX).asciidoc")],
    },
    {
        "name": "ZIP Archive",
        "short_name": "ZIP",
        "category": "archive",
        "forensic_relevance": (
            "General-purpose archive. iOS IPA app packages, Android APKs, "
            "Office documents (DOCX/XLSX), and many other compound formats are ZIPs."
        ),
        "platforms": "iOS,macOS,Android,Cross-platform",
        "parser_class": None,
        "magic": [(0, b"PK\x03\x04")],
        "extensions": [".zip", ".ipa", ".apk", ".docx", ".xlsx", ".pptx", ".jar"],
        "links": [("Format spec", "https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT")],
    },
    {
        "name": "TAR Archive",
        "short_name": "TAR",
        "category": "archive",
        "forensic_relevance": (
            "Common archive for Android ADB backups and Linux filesystem images. "
            "Often compressed as .tar.gz or .tar.bz2."
        ),
        "platforms": "Android,Cross-platform",
        "parser_class": None,
        "magic": [(257, b"ustar")],
        "extensions": [".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz"],
        "links": [("Format spec", "https://www.gnu.org/software/tar/manual/html_node/Standard.html")],
    },
    {
        "name": "Mach-O Executable",
        "short_name": "Mach-O",
        "category": "executable",
        "forensic_relevance": (
            "iOS and macOS native executable format. App binaries can be analysed "
            "for hardcoded strings, URLs, encryption keys, and entitlements."
        ),
        "platforms": "iOS,macOS",
        "parser_class": None,
        "magic": [(0, b"\xce\xfa\xed\xfe")],
        "extensions": ["", ".dylib", ".framework"],
        "links": [("Developer docs", "https://developer.apple.com/library/archive/documentation/Performance/Conceptual/CodeFootprint/Articles/MachOOverview.html")],
    },
    {
        "name": "ELF Executable",
        "short_name": "ELF",
        "category": "executable",
        "forensic_relevance": (
            "Android and Linux native executable format. "
            "Shared libraries (.so) and binaries can be reverse-engineered."
        ),
        "platforms": "Android",
        "parser_class": None,
        "magic": [(0, b"\x7fELF")],
        "extensions": [".so", ".elf"],
        "links": [("Format spec", "https://man7.org/linux/man-pages/man5/elf.5.html")],
    },
    {
        "name": "Apple Disk Image (DMG)",
        "short_name": "DMG",
        "category": "archive",
        "forensic_relevance": (
            "macOS disk image format used for app distribution and backups. "
            "May contain HFS+ or APFS filesystems requiring separate mounting."
        ),
        "platforms": "macOS",
        "parser_class": None,
        "magic": [(0, b"koly")],
        "extensions": [".dmg"],
        "links": [("Research", "https://newosxbook.com/DMG.html")],
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
        "platforms": "iOS,macOS,Android,Cross-platform",
        "parser_class": None,
        "magic": [(0, b"\x37\x7f\x06\x83")],
        "extensions": [".db-wal", ".sqlite-wal", ".sqlite3-wal"],
        "links": [("Format spec", "https://www.sqlite.org/walformat.html")],
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
            offset      INTEGER NOT NULL DEFAULT 0,
            pattern     BLOB NOT NULL
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

    for fmt in FORMATS:
        cur = conn.execute(
            "INSERT INTO formats (name, short_name, category, forensic_relevance, "
            "platforms, parser_class) VALUES (?,?,?,?,?,?)",
            (
                fmt["name"],
                fmt.get("short_name", ""),
                fmt.get("category", ""),
                fmt.get("forensic_relevance", ""),
                fmt.get("platforms", ""),
                fmt.get("parser_class"),
            ),
        )
        fid = cur.lastrowid
        for offset, pattern in fmt.get("magic", []):
            conn.execute(
                "INSERT INTO magic_bytes (format_id, offset, pattern) VALUES (?,?,?)",
                (fid, offset, pattern),
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
    print(f"Built {out_path}  ({len(FORMATS)} formats)")


if __name__ == "__main__":
    build()
