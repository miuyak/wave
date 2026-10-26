"""Entry point: `python -m wavestudio` or `python main.py`."""
import sys


def main():
    from pathlib import Path

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from . import APP_NAME
    from .ui.main_window import MainWindow
    from .ui.style import apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    apply_theme(app)

    assets = Path(__file__).resolve().parent.parent / "assets"
    icon = QIcon()
    for size in (16, 32, 48, 64, 128, 256, 512):
        fp = assets / f"icon_{size}.png"
        if fp.exists():
            icon.addFile(str(fp))
    app.setWindowIcon(icon)
    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
