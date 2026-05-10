"""Entry point."""
import os
import sys


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
