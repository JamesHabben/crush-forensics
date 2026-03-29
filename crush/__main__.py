"""Entry point."""
import sys

def main() -> None:
    import crush
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
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
