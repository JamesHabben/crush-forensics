# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Registers all built-in parsers in priority order.

Specific parsers go first. HexFallbackParser must always be last —
it matches everything and acts as a catch-all.
"""
from crush.core.registry import ParserRegistry
from crush.parsers.sqlite_parser import SQLiteParser
from crush.parsers.xml_parser import XmlParser
from crush.parsers.plist_parser import PlistParser
from crush.parsers.abx_parser import AbxParser
from crush.parsers.segb_parser import SegbParser
from crush.parsers.leveldb_parser import LeveldbParser
from crush.parsers.image_parser import ImageParser
from crush.parsers.media_parser import MediaParser
from crush.parsers.json_parser import JsonParser
from crush.parsers.hex_fallback import HexFallbackParser

ParserRegistry.register(SQLiteParser())
ParserRegistry.register(XmlParser())
ParserRegistry.register(PlistParser())
ParserRegistry.register(AbxParser())
ParserRegistry.register(SegbParser())
ParserRegistry.register(LeveldbParser())
ParserRegistry.register(ImageParser())
ParserRegistry.register(MediaParser())
ParserRegistry.register(JsonParser())
ParserRegistry.register(HexFallbackParser())  # Must be last
