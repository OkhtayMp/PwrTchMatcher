from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .constants import APP_NAME
from .window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("OkhtayMp")
    app.setStyleSheet("")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
