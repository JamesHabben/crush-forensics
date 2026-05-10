"""Entry point."""
import os
import sys


def _install_xdg_url_handler(app: "QApplication") -> None:  # type: ignore[name-defined]
    """On Linux, replace Qt's QDesktopServices URL handler with one that strips
    AppImage-injected LD_LIBRARY_PATH before calling xdg-open.  Without this,
    xdg-open inherits the AppImage library paths and silently fails to open both
    local files and http/https links.  Registered for http, https, and file so
    every openUrl call — including those fired by setOpenExternalLinks(True) —
    goes through the same clean environment.
    """
    import subprocess
    from PySide6.QtCore import QObject, QUrl, Slot
    from PySide6.QtGui import QDesktopServices

    class _XdgHandler(QObject):
        @Slot(QUrl)
        def open(self, url: QUrl) -> None:
            env = {k: v for k, v in os.environ.items()
                   if k not in ("LD_LIBRARY_PATH", "LD_PRELOAD")}
            subprocess.Popen(
                ["xdg-open", url.toString()],
                env=env,
                close_fds=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    handler = _XdgHandler(app)
    for scheme in ("http", "https", "file"):
        QDesktopServices.setUrlHandler(scheme, handler, "open")


def _icon_path() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.join(sys._MEIPASS, "crush", "resources", "icons")  # type: ignore[attr-defined]
        for name in ("crush_icon_256.png", "crush_icon_128.svg"):
            p = os.path.join(base, name)
            if os.path.exists(p):
                return p
        return ""
    return os.path.join(os.path.dirname(__file__), "resources", "icons", "crush_icon_128.svg")


def main() -> None:
    import crush
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from crush.ui.main_window import MainWindow
    app = QApplication(sys.argv)
    if sys.platform.startswith("linux"):
        _install_xdg_url_handler(app)
    # On Windows the native style partially ignores QPalette for menus, causing
    # the menu background/text colors to conflict with the app theme.  Fusion is
    # Qt's cross-platform style that honours QPalette fully on every OS.
    if sys.platform.startswith("win"):
        app.setStyle("Fusion")
    app.setApplicationName("Crush")
    app.setApplicationVersion(crush.display_version())
    app.setOrganizationName("Crush DFIR")
    app.setDesktopFileName("crush")  # Wayland app-id → taskbar icon association
    icon_path = _icon_path()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
