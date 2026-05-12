# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
import subprocess
import sys


def open_url(url: str) -> None:
    """Open *url* with the system default handler.

    On Linux, QDesktopServices.openUrl spawns xdg-open with the AppImage-modified
    LD_LIBRARY_PATH, which causes it to fail silently.  Use xdg-open directly with
    a cleaned environment instead.
    """
    if sys.platform.startswith("linux"):
        env = {k: v for k, v in os.environ.items()
               if k not in ("LD_LIBRARY_PATH", "LD_PRELOAD")}
        try:
            subprocess.Popen(
                ["xdg-open", url],
                env=env,
                close_fds=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    QDesktopServices.openUrl(QUrl(url))
