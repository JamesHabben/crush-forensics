# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""Value Inspector — flat interpretation panel for text/numeric cell values."""
from __future__ import annotations

import struct
import uuid as _uuid_mod
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import Qt
from PySide6.QtGui import QClipboard, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_MUTED = QColor(140, 140, 140)
_GROUP_BG = QColor(240, 240, 240)

# Reference epochs
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_COCOA_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)
_CHROME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)
_HFS_EPOCH = datetime(1904, 1, 1, tzinfo=timezone.utc)

# Plausible timestamp ranges: 1990-01-01 to 2100-01-01 (Unix seconds)
_TS_S_MIN, _TS_S_MAX = 631_152_000, 4_102_444_800
_TS_MS_MIN, _TS_MS_MAX = _TS_S_MIN * 1_000, _TS_S_MAX * 1_000
_TS_US_MIN, _TS_US_MAX = _TS_S_MIN * 1_000_000, _TS_S_MAX * 1_000_000

# Cocoa: seconds since 2001-01-01; Cocoa epoch is 978_307_200s after Unix epoch
_COCOA_OFFSET = 978_307_200
_COCOA_MIN = _TS_S_MIN - _COCOA_OFFSET
_COCOA_MAX = _TS_S_MAX - _COCOA_OFFSET

# Chrome/WebKit: µs since 1601-01-01
_CHROME_US_MIN = 12_591_158_400_000_000
_CHROME_US_MAX = 15_778_476_000_000_000

# Windows FILETIME: 100ns intervals since 1601-01-01
_WIN_FT_MIN = _CHROME_US_MIN * 10
_WIN_FT_MAX = _CHROME_US_MAX * 10

# HFS+: seconds since 1904-01-01; offset from Unix epoch
_HFS_OFFSET = 2_082_844_800
_HFS_MIN = _TS_S_MIN + _HFS_OFFSET
_HFS_MAX = _TS_S_MAX + _HFS_OFFSET


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _safe_ts(ts_s: float) -> str | None:
    try:
        return _fmt_dt(datetime.fromtimestamp(ts_s, tz=timezone.utc))
    except (OSError, OverflowError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Interpretation engine
# ---------------------------------------------------------------------------

class _Row:
    __slots__ = ("group", "label", "value")

    def __init__(self, group: str, label: str, value: str | None) -> None:
        self.group = group
        self.label = label
        self.value = value


def _interpret(raw: str) -> list[_Row]:
    rows: list[_Row] = []
    raw = raw.strip()
    if not raw:
        return rows

    R = _Row

    # --- Parse attempts ---
    int_val: int | None = None
    try:
        int_val = int(raw, 0) if raw.startswith(("0x", "0X")) else int(raw)
    except (ValueError, OverflowError):
        pass

    float_val: float | None = None
    try:
        float_val = float(raw)
    except ValueError:
        pass

    # Hex-clean: only keep hex digits, detect if input looks like a hex string
    hex_clean = "".join(c for c in raw.lower() if c in "0123456789abcdef")
    # Truncate to even number of nibbles (e.g. "f7 f8 f" → "f7f8", not a parse error)
    if len(hex_clean) % 2 != 0:
        hex_clean = hex_clean[:-1]
    is_hex_str = (
        all(c in "0123456789abcdefABCDEF:- " for c in raw)
        and bool(hex_clean)
    )
    # Integer value of bare hex string (e.g. "c0a80101" or "f7 f8 f9 fa" without 0x prefix)
    hex_int_val: int | None = None
    hex_le_int_val: int | None = None
    hex_bytes_val: bytes | None = None
    if is_hex_str and int_val is None and hex_clean:
        try:
            hex_int_val = int(hex_clean, 16)
            hex_bytes_val = bytes.fromhex(hex_clean)
            hex_le_int_val = int.from_bytes(hex_bytes_val, "little")
        except ValueError:
            pass

    # -----------------------------------------------------------------------
    # Group: Integer
    # -----------------------------------------------------------------------
    # Use decimal int if available, fall back to big-endian interpretation of hex bytes
    eff_int = int_val if int_val is not None else hex_int_val

    if eff_int is not None:
        rows.append(R("Integer", "Decimal", f"{eff_int:,}"))
        rows.append(R("Integer", "Hex", hex(eff_int)))
        if 0 <= eff_int <= 0xFFFF_FFFF:
            s32 = eff_int if eff_int < 0x8000_0000 else eff_int - 0x1_0000_0000
            rows.append(R("Integer", "Signed 32-bit", str(s32)))
            rows.append(R("Integer", "Unsigned 32-bit", str(eff_int)))
        else:
            rows.append(R("Integer", "Signed 32-bit", None))
            rows.append(R("Integer", "Unsigned 32-bit", None))
        if -(2**63) <= eff_int <= 2**63 - 1:
            rows.append(R("Integer", "Signed 64-bit", str(eff_int)))
        else:
            rows.append(R("Integer", "Signed 64-bit", None))
        if 0 <= eff_int <= 2**64 - 1:
            rows.append(R("Integer", "Unsigned 64-bit", str(eff_int)))
        else:
            rows.append(R("Integer", "Unsigned 64-bit", None))
    else:
        for lbl in ("Decimal", "Hex", "Signed 32-bit", "Unsigned 32-bit", "Signed 64-bit", "Unsigned 64-bit"):
            rows.append(R("Integer", lbl, None))

    # Little-endian variants — only shown for hex byte inputs (not decimal)
    if hex_le_int_val is not None and int_val is None:
        le = hex_le_int_val
        rows.append(R("Integer", "Decimal (LE)", f"{le:,}"))
        rows.append(R("Integer", "Hex (LE)", hex(le)))
        if 0 <= le <= 0xFFFF_FFFF:
            s32 = le if le < 0x8000_0000 else le - 0x1_0000_0000
            rows.append(R("Integer", "Signed 32-bit (LE)", str(s32)))
            rows.append(R("Integer", "Unsigned 32-bit (LE)", str(le)))
        else:
            rows.append(R("Integer", "Signed 32-bit (LE)", None))
            rows.append(R("Integer", "Unsigned 32-bit (LE)", None))
        if -(2**63) <= le <= 2**63 - 1:
            rows.append(R("Integer", "Signed 64-bit (LE)", str(le)))
        else:
            rows.append(R("Integer", "Signed 64-bit (LE)", None))
        if 0 <= le <= 2**64 - 1:
            rows.append(R("Integer", "Unsigned 64-bit (LE)", str(le)))
        else:
            rows.append(R("Integer", "Unsigned 64-bit (LE)", None))

    # -----------------------------------------------------------------------
    # Group: Float
    # -----------------------------------------------------------------------
    if float_val is not None and int_val is None:
        rows.append(R("Float", "Double (64-bit)", f"{float_val:.17g}"))
    else:
        rows.append(R("Float", "Double (64-bit)", None))

    if eff_int is not None and 0 <= eff_int <= 0xFFFF_FFFF:
        f32 = struct.unpack(">f", eff_int.to_bytes(4, "big"))[0]
        rows.append(R("Float", "Float32 · 4 bytes BE", f"{f32:.9g}"))
    else:
        rows.append(R("Float", "Float32 · 4 bytes BE", None))

    if hex_bytes_val is not None and len(hex_bytes_val) == 4:
        f32_le = struct.unpack("<f", hex_bytes_val)[0]
        rows.append(R("Float", "Float32 · 4 bytes LE", f"{f32_le:.9g}"))
    else:
        rows.append(R("Float", "Float32 · 4 bytes LE", None))

    if eff_int is not None and 0 <= eff_int <= 2**64 - 1:
        try:
            f64 = struct.unpack(">d", eff_int.to_bytes(8, "big"))[0]
            rows.append(R("Float", "Double · 8 bytes BE", f"{f64:.17g}"))
        except struct.error:
            rows.append(R("Float", "Double · 8 bytes BE", None))
    else:
        rows.append(R("Float", "Double · 8 bytes BE", None))

    if hex_bytes_val is not None and len(hex_bytes_val) == 8:
        try:
            f64_le = struct.unpack("<d", hex_bytes_val)[0]
            rows.append(R("Float", "Double · 8 bytes LE", f"{f64_le:.17g}"))
        except struct.error:
            rows.append(R("Float", "Double · 8 bytes LE", None))
    else:
        rows.append(R("Float", "Double · 8 bytes LE", None))

    # -----------------------------------------------------------------------
    # Group: Timestamps
    # -----------------------------------------------------------------------
    ts = eff_int

    if ts is not None and _TS_S_MIN <= ts <= _TS_S_MAX:
        rows.append(R("Timestamp", "Unix (s)", _safe_ts(ts)))
    else:
        rows.append(R("Timestamp", "Unix (s)", None))

    if ts is not None and _TS_MS_MIN <= ts <= _TS_MS_MAX:
        rows.append(R("Timestamp", "Unix (ms)", _safe_ts(ts / 1_000)))
    else:
        rows.append(R("Timestamp", "Unix (ms)", None))

    if ts is not None and _TS_US_MIN <= ts <= _TS_US_MAX:
        rows.append(R("Timestamp", "Unix (µs)", _safe_ts(ts / 1_000_000)))
    else:
        rows.append(R("Timestamp", "Unix (µs)", None))

    # Cocoa: seconds since 2001-01-01; for floats require > 1M to avoid false positives on tiny values
    cocoa_src = ts if ts is not None else (float_val if float_val is not None and float_val > 1_000_000 else None)
    if cocoa_src is not None and _COCOA_MIN <= cocoa_src <= _COCOA_MAX:
        try:
            rows.append(R("Timestamp", "Cocoa / Apple (s)", _fmt_dt(_COCOA_EPOCH + timedelta(seconds=cocoa_src))))
        except (OverflowError, ValueError):
            rows.append(R("Timestamp", "Cocoa / Apple (s)", None))
    else:
        rows.append(R("Timestamp", "Cocoa / Apple (s)", None))

    # Chrome / WebKit: µs since 1601-01-01
    if ts is not None and _CHROME_US_MIN <= ts <= _CHROME_US_MAX:
        try:
            rows.append(R("Timestamp", "Chrome / WebKit (µs)", _fmt_dt(_CHROME_EPOCH + timedelta(microseconds=ts))))
        except (OverflowError, ValueError):
            rows.append(R("Timestamp", "Chrome / WebKit (µs)", None))
    else:
        rows.append(R("Timestamp", "Chrome / WebKit (µs)", None))

    # Windows FILETIME: 100ns intervals since 1601-01-01
    if ts is not None and _WIN_FT_MIN <= ts <= _WIN_FT_MAX:
        try:
            rows.append(R("Timestamp", "Windows FILETIME", _fmt_dt(_CHROME_EPOCH + timedelta(microseconds=ts / 10))))
        except (OverflowError, ValueError):
            rows.append(R("Timestamp", "Windows FILETIME", None))
    else:
        rows.append(R("Timestamp", "Windows FILETIME", None))

    # HFS+: seconds since 1904-01-01
    if ts is not None and _HFS_MIN <= ts <= _HFS_MAX:
        try:
            rows.append(R("Timestamp", "HFS+ / Mac OS (s)", _fmt_dt(_HFS_EPOCH + timedelta(seconds=ts))))
        except (OverflowError, ValueError):
            rows.append(R("Timestamp", "HFS+ / Mac OS (s)", None))
    else:
        rows.append(R("Timestamp", "HFS+ / Mac OS (s)", None))

    # -----------------------------------------------------------------------
    # Group: UUID
    # -----------------------------------------------------------------------
    uuid_val: str | None = None
    if len(raw) == 36 and raw.count("-") == 4:
        try:
            uuid_val = str(_uuid_mod.UUID(raw))
        except ValueError:
            pass
    elif is_hex_str and len(hex_clean) == 32:
        try:
            uuid_val = str(_uuid_mod.UUID(hex_clean))
        except ValueError:
            pass
    rows.append(R("UUID", "UUID", uuid_val))

    # -----------------------------------------------------------------------
    # Group: Network
    # -----------------------------------------------------------------------
    ipv4_src = eff_int if eff_int is not None and len(hex_clean) <= 8 else None
    if ipv4_src is not None and 0 <= ipv4_src <= 0xFFFF_FFFF:
        b_be = ipv4_src.to_bytes(4, "big")
        b_le = ipv4_src.to_bytes(4, "little")
        rows.append(R("Network", "IPv4 (big-endian)", ".".join(str(x) for x in b_be)))
        rows.append(R("Network", "IPv4 (little-endian)", ".".join(str(x) for x in b_le)))
    else:
        rows.append(R("Network", "IPv4 (big-endian)", None))
        rows.append(R("Network", "IPv4 (little-endian)", None))

    mac_val: str | None = None
    if is_hex_str and len(hex_clean) == 12:
        mac_val = ":".join(hex_clean[i:i + 2] for i in range(0, 12, 2))
    elif len(raw) == 17 and raw.count(":") == 5:
        mac_val = raw.lower()
    rows.append(R("Network", "MAC address", mac_val))

    # -----------------------------------------------------------------------
    # Group: Text
    # -----------------------------------------------------------------------
    if hex_bytes_val:
        ascii_text = "".join(chr(b) if 32 <= b < 127 else "." for b in hex_bytes_val)
        rows.append(R("Text", "ASCII (hex bytes)", ascii_text))
        try:
            utf8_text = hex_bytes_val.decode("utf-8")
            rows.append(R("Text", "UTF-8 (hex bytes)", utf8_text))
        except UnicodeDecodeError:
            rows.append(R("Text", "UTF-8 (hex bytes)", None))

    return rows


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------

_instance: "ValueInspector | None" = None


def _clear_instance() -> None:
    global _instance
    _instance = None


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class ValueInspector(QDialog):
    """Non-modal singleton dialog showing all interpretations of a text/numeric value."""

    @staticmethod
    def inspect(value: str, parent: QWidget | None = None) -> None:
        global _instance
        if _instance is None:
            _instance = ValueInspector(parent)
            _instance.show()
        _instance._set_value(value)
        _instance.raise_()
        _instance.activateWindow()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Value Inspector")
        self.resize(500, 560)
        self.destroyed.connect(_clear_instance)
        self._build_ui()
        # Connect to X11 PRIMARY selection (Linux); fires when user highlights text anywhere
        clipboard = QApplication.clipboard()
        if clipboard.supportsSelection():
            clipboard.selectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self) -> None:
        focused = QApplication.focusWidget()
        if focused is None:
            return  # another application has focus — ignore external selections
        if focused is self or self.isAncestorOf(focused):
            return  # selection came from within the inspector itself
        text = QApplication.clipboard().text(QClipboard.Mode.Selection).strip()
        if text:
            self._set_value(text)

    def closeEvent(self, event: object) -> None:
        clipboard = QApplication.clipboard()
        if clipboard.supportsSelection():
            try:
                clipboard.selectionChanged.disconnect(self._on_selection_changed)
            except RuntimeError:
                pass
        super().closeEvent(event)  # type: ignore[arg-type]

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(8)
        outer.setContentsMargins(8, 8, 8, 8)

        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("Value:"))
        self._input = QLineEdit()
        self._input.setPlaceholderText("Enter or paste a value…")
        self._input.textChanged.connect(self._refresh)
        input_row.addWidget(self._input)
        outer.addLayout(input_row)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Interpretation", "Value"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setDefaultSectionSize(190)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        outer.addWidget(self._table)

        bottom = QHBoxLayout()
        copy_btn = QPushButton("Copy value")
        copy_btn.clicked.connect(self._copy_selected)
        bottom.addWidget(copy_btn)
        bottom.addStretch()
        outer.addLayout(bottom)

    def _set_value(self, value: str) -> None:
        self._input.blockSignals(True)
        self._input.setText(value.strip())
        self._input.blockSignals(False)
        self._refresh(value.strip())

    def _refresh(self, text: str = "") -> None:
        rows = _interpret(text or self._input.text())

        bold = QFont()
        bold.setBold(True)

        # Flatten rows into display items, inserting group headers
        items: list[tuple[bool, str, str | None]] = []
        prev_group: str | None = None
        for row in rows:
            if row.group != prev_group:
                items.append((True, row.group, None))
                prev_group = row.group
            items.append((False, row.label, row.value))

        self._table.setRowCount(len(items))
        for i, (is_header, label, value) in enumerate(items):
            if is_header:
                for col, text in enumerate((label, "")):
                    item = QTableWidgetItem(text)
                    item.setFont(bold)
                    item.setBackground(_GROUP_BG)
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    self._table.setItem(i, col, item)
                self._table.setRowHeight(i, 20)
            else:
                applicable = value is not None
                val_text = value if applicable else "—"
                lbl_item = QTableWidgetItem(label)
                val_item = QTableWidgetItem(val_text)
                lbl_item.setToolTip(label)
                val_item.setToolTip(val_text)
                if not applicable:
                    lbl_item.setForeground(_MUTED)
                    val_item.setForeground(_MUTED)
                for col, item in enumerate((lbl_item, val_item)):
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    self._table.setItem(i, col, item)

    def _copy_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        item = self._table.item(row, 1)
        if item and item.text() and item.text() != "—":
            QApplication.clipboard().setText(item.text())
