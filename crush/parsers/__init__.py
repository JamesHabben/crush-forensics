# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Registers all built-in parsers in priority order.

Specific parsers go first. HexFallbackParser must always be last —
it matches everything and acts as a catch-all.
"""
from crush.core.registry import ParserRegistry
from crush.parsers.sqlite_parser import SQLiteParser
from crush.parsers.plist_parser import PlistParser
from crush.parsers.abx_parser import AbxParser
from crush.parsers.xml_parser import XmlParser
from crush.parsers.hex_fallback import HexFallbackParser

ParserRegistry.register(SQLiteParser())
ParserRegistry.register(PlistParser())
ParserRegistry.register(AbxParser())
ParserRegistry.register(XmlParser())
ParserRegistry.register(HexFallbackParser())  # Must be last
