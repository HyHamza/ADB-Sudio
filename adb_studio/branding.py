"""Application icon resolution and Windows Taskbar AppUserModelID setup."""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap


def set_windows_app_id(app_id: str = "Hamza.ADBStudio.1.0") -> None:
    """Set explicit AppUserModelID so Windows Taskbar uses our app icon, not python.exe."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError):
        pass


def resolve_icon_path() -> Path | None:
    """Return the path to `assets/adb_studio.ico` in dev or PyInstaller frozen mode."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    ico = base / "assets" / "adb_studio.ico"
    if ico.exists():
        return ico
    png = base / "assets" / "adb_studio.png"
    if png.exists():
        return png
    return None


def load_app_icon() -> QIcon:
    """Load the multi-resolution app icon, falling back to a painted badge if missing."""
    icon_path = resolve_icon_path()
    if icon_path is not None:
        icon = QIcon(str(icon_path))
        if not icon.isNull():
            return icon

    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#2563eb"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 14, 14)
    painter.setPen(QColor("#ffffff"))
    painter.setFont(QFont("Segoe UI", 18, QFont.Bold))
    painter.drawText(pix.rect(), Qt.AlignCenter, "ADB")
    painter.end()
    return QIcon(pix)
