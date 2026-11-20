"""Floating top-of-screen HUD pill overlay for global screenshot status feedback."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class ScreenshotHudToast(QWidget):
    """Non-focus-stealing floating pill at top-center of screen."""

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._accent = QColor("#3b82f6")
        self._bg = QColor(17, 22, 29, 238)
        self._border = QColor("#303c4d")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 10, 20, 10)
        layout.setSpacing(10)

        self._dot = QLabel("●")
        self._dot.setStyleSheet("color: #3b82f6; font-size: 13px; background: transparent;")
        self._label = QLabel("Taking screenshot...")
        self._label.setStyleSheet(
            "color: #f8fafc; font-family: 'Segoe UI'; font-size: 13px; "
            "font-weight: 600; background: transparent;"
        )
        layout.addWidget(self._dot)
        layout.addWidget(self._label)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._slide_out)

        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._hide_on_anim_end = False
        self._anim.finished.connect(self._on_anim_finished)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        radius = rect.height() / 2.0
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, self._bg)
        painter.setPen(self._border)
        painter.drawPath(path)

    def _target_positions(self) -> tuple[QPoint, QPoint]:
        screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else self.rect()
        x = geo.x() + (geo.width() - self.width()) // 2
        hidden_y = geo.y() - self.height() - 12
        shown_y = geo.y() + 18
        return QPoint(x, hidden_y), QPoint(x, shown_y)

    def _present(self, text: str, accent_hex: str, border_hex: str, auto_hide_ms: int = 0) -> None:
        self._hide_timer.stop()
        self._anim.stop()
        self._hide_on_anim_end = False

        self._dot.setStyleSheet(f"color: {accent_hex}; font-size: 13px; background: transparent;")
        self._border = QColor(border_hex)
        self._label.setText(text)
        self.adjustSize()

        hidden_pos, shown_pos = self._target_positions()
        if not self.isVisible():
            self.move(hidden_pos)
            self.show()

        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(shown_pos)
        self._anim.start()
        self.update()

        if auto_hide_ms > 0:
            self._hide_timer.start(auto_hide_ms)

    def _slide_out(self) -> None:
        self._anim.stop()
        self._hide_on_anim_end = True
        hidden_pos, _ = self._target_positions()
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(hidden_pos)
        self._anim.start()

    def _on_anim_finished(self) -> None:
        if self._hide_on_anim_end:
            self._hide_on_anim_end = False
            self.hide()

    def show_capturing(self) -> None:
        """Slide down the pill showing capture in progress."""
        self._present("Taking screenshot...", "#3b82f6", "#2563eb", auto_hide_ms=0)

    def show_captured(self, copied: bool = True) -> None:
        """Update the pill to completion state and auto-hide."""
        text = "Captured & Copied to Clipboard" if copied else "Screenshot Saved"
        self._present(text, "#10b981", "#059669", auto_hide_ms=2200)

    def show_error(self, message: str = "Screenshot Failed") -> None:
        """Show error state briefly and auto-hide."""
        self._present(message, "#ef4444", "#b91c1c", auto_hide_ms=2500)
