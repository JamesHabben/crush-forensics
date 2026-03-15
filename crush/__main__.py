"""Entry point."""
import sys

def main() -> None:
    from PySide6.QtWidgets import QApplication
    from crush.ui.main_window import MainWindow
    app = QApplication(sys.argv)
    app.setApplicationName("Crush")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("Crush DFIR")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
