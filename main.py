"""Application entry point for ADB Studio."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from adb_studio.branding import load_app_icon, set_windows_app_id
from adb_studio.ui.main_window import MainWindow
from adb_studio.ui.styles import DARK_STYLESHEET


def main() -> int:
    """Launch the ADB Studio desktop application."""
    set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("ADB Studio")
    app.setWindowIcon(load_app_icon())
    app.setStyleSheet(DARK_STYLESHEET)

    start_minimized = "--minimized" in sys.argv[1:]
    window = MainWindow()
    if start_minimized and window.tray_available():
        window.hide()
        window.show_tray_message(
            "ADB Studio",
            "Running in background. Press your global hotkey to take a screenshot.",
        )
    else:
        window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
