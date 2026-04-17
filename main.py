"""SEM MM — Massive Measurement entry point.

Windows multiprocessing requires the freeze-safe guard below.
"""

import sys
from multiprocessing import freeze_support


def main() -> None:
    from PyQt6.QtWidgets import QApplication
    from src.gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("SEM MM")
    app.setOrganizationName("SEM-Tools")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    freeze_support()   # required for PyInstaller / Windows multiprocessing
    main()
