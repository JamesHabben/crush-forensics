"""Entry point."""
import os
import sys


def _icon_path() -> str:
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.dirname(__file__)
        return os.path.join(base, "resources", "icons", "crush_icon_128.svg")
    return os.path.join(base, "crush", "resources", "icons", "crush_icon_128.svg")


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
    icon_path = _icon_path()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
