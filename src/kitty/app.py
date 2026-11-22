from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from kitty.main_window import MainWindow


def main() -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("Kitty")
    application.setOrganizationName("Kitty")
    window = MainWindow()
    window.show()
    return application.exec()

