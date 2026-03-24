# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 - now Marco Neumann (kalink0)
"""About dialog — version info and third-party acknowledgements."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

import crush

_ABOUT_HTML = f"""\
<h2>Crush {crush.__version__}</h2>
<p><b>Digital Forensic Analysis Workbench</b></p>
<p>Open-source tool for parsing and examining digital forensic artefacts
from iOS, macOS, Android, and other platforms.</p>
<p>Licensed under the <b>Apache License 2.0</b></p>
<p><a href="https://github.com/kalink0/crush-forensics">
github.com/kalink0/crush-forensics</a></p>
"""

_ACK_BODY = """\
<h3>Bundled third-party code</h3>
<table>
  <tr>
    <td><b>ccl_bplist</b></td>
    <td>Binary plist parser</td>
    <td class="lic">BSD 3-Clause</td>
    <td><a href="https://github.com/cclgroupltd/ccl-bplist">CCL Forensics</a></td>
  </tr>
  <tr class="alt">
    <td><b>ccl_segb</b></td>
    <td>SEGB (Significant Energy Bearer) parser</td>
    <td class="lic">MIT</td>
    <td><a href="https://github.com/cclgroupltd/ccl_segb">CCL Forensics</a></td>
  </tr>
  <tr>
    <td><b>ccl_leveldb</b></td>
    <td>LevelDB / Chrome LevelDB parser</td>
    <td class="lic">MIT</td>
    <td><a href="https://github.com/cclgroupltd/ccl-leveldb">CCL Forensics</a></td>
  </tr>
</table>

<h3>Python package dependencies</h3>
<table>
  <tr>
    <td><b>PySide6</b></td>
    <td>Qt for Python — GUI framework</td>
    <td class="lic">LGPL v3</td>
    <td><a href="https://doc.qt.io/qtforpython/">qt.io</a></td>
  </tr>
  <tr class="alt">
    <td><b>biplist</b></td>
    <td>Binary plist read/write</td>
    <td class="lic">BSD</td>
    <td><a href="https://github.com/wooster/biplist">wooster/biplist</a></td>
  </tr>
  <tr>
    <td><b>lxml</b></td>
    <td>XML and HTML processing</td>
    <td class="lic">BSD</td>
    <td><a href="https://lxml.de/">lxml.de</a></td>
  </tr>
  <tr class="alt">
    <td><b>construct</b></td>
    <td>Binary data structure parsing</td>
    <td class="lic">MIT</td>
    <td><a href="https://construct.readthedocs.io/">construct</a></td>
  </tr>
  <tr>
    <td><b>python-magic</b></td>
    <td>File type detection via libmagic</td>
    <td class="lic">MIT</td>
    <td><a href="https://github.com/ahupp/python-magic">ahupp/python-magic</a></td>
  </tr>
  <tr class="alt">
    <td><b>filetype</b></td>
    <td>File type and MIME detection</td>
    <td class="lic">MIT</td>
    <td><a href="https://github.com/h2non/filetype.py">h2non/filetype.py</a></td>
  </tr>
  <tr>
    <td><b>pypdf</b></td>
    <td>PDF reading and text extraction</td>
    <td class="lic">BSD 3-Clause</td>
    <td><a href="https://pypdf.readthedocs.io/">pypdf</a></td>
  </tr>
</table>
"""


def _ack_html(browser: QTextBrowser) -> str:
    """Build acknowledgements HTML with colors drawn from the widget palette."""
    pal = browser.palette()
    text = pal.color(QPalette.ColorRole.Text).name()
    muted = pal.color(QPalette.ColorRole.PlaceholderText).name()
    alt_bg = pal.color(QPalette.ColorRole.AlternateBase).name()
    return f"""\
<style>
  body  {{ font-family: sans-serif; font-size: 13px; color: {text}; }}
  h3    {{ margin-top: 16px; margin-bottom: 4px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  td    {{ padding: 4px 8px; vertical-align: top; }}
  tr.alt td {{ background: {alt_bg}; }}
  .lic  {{ color: {muted}; font-size: 12px; }}
</style>
{_ACK_BODY}"""


class AboutDialog(QDialog):
    """Tabbed About dialog with version info and third-party acknowledgements."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About Crush")
        self.resize(620, 420)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        # --- About tab ---
        about_widget = QWidget()
        about_layout = QVBoxLayout(about_widget)
        about_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        about_label = QLabel(_ABOUT_HTML)
        about_label.setOpenExternalLinks(True)
        about_label.setWordWrap(True)
        about_label.setTextFormat(Qt.TextFormat.RichText)
        about_layout.addWidget(about_label)
        about_layout.addStretch()
        tabs.addTab(about_widget, "About")

        # --- Acknowledgements tab ---
        ack_browser = QTextBrowser()
        ack_browser.setOpenExternalLinks(True)
        ack_browser.setHtml(_ack_html(ack_browser))
        tabs.addTab(ack_browser, "Acknowledgements")

        layout.addWidget(tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
