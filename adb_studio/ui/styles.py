"""Dark modern QSS stylesheet for ADB Studio."""

DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #11161d;
    color: #e6edf3;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}

QGroupBox {
    background-color: #161d26;
    border: 1px solid #26303d;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
    color: #9fb0c3;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    background-color: #161d26;
    color: #c9d6e3;
}

QPushButton {
    background-color: #1f2937;
    border: 1px solid #303c4d;
    border-radius: 6px;
    padding: 6px 12px;
    min-height: 20px;
    color: #e6edf3;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #293548;
    border-color: #4b5e77;
}

QPushButton:pressed {
    background-color: #17202b;
}

QPushButton:disabled {
    background-color: #151b23;
    border-color: #222a35;
    color: #556272;
}

QPushButton#primaryBtn {
    background-color: #2563eb;
    border: 1px solid #3b82f6;
    color: #ffffff;
    font-weight: 600;
    padding: 10px 16px;
    font-size: 14px;
}

QPushButton#primaryBtn:hover {
    background-color: #1d4ed8;
}

QPushButton#primaryBtn:disabled {
    background-color: #1b283f;
    border-color: #243554;
    color: #6b7f9c;
}

QPushButton#dangerBtn {
    background-color: #3a1c22;
    border: 1px solid #7f2937;
    color: #fca5a5;
}

QPushButton#dangerBtn:hover {
    background-color: #52232c;
    border-color: #ef4444;
}

QPushButton#dangerBtn:disabled {
    background-color: #1c1619;
    border-color: #2d2024;
    color: #6b4c52;
}

QLineEdit, QComboBox, QSpinBox {
    background-color: #0d1218;
    border: 1px solid #2a3442;
    border-radius: 6px;
    padding: 6px 9px;
    color: #e6edf3;
    selection-background-color: #2563eb;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #3b82f6;
}

QListWidget, QPlainTextEdit {
    background-color: #0d1218;
    border: 1px solid #26303d;
    border-radius: 6px;
    padding: 4px;
    color: #e6edf3;
    selection-background-color: #1f3b64;
}

QListWidget::item {
    padding: 7px 8px;
    border-radius: 5px;
    margin: 2px 0;
}

QListWidget::item:selected {
    background-color: #1e3a5f;
    border: 1px solid #3b82f6;
}

QPlainTextEdit#consoleLog {
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
    color: #c9d6e3;
}

QTabWidget::pane {
    border: 1px solid #26303d;
    border-radius: 8px;
    background-color: #161d26;
    padding: 8px;
}

QTabBar::tab {
    background-color: #161d26;
    border: 1px solid #26303d;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 7px 14px;
    margin-right: 4px;
    color: #8b9bb0;
    font-weight: 500;
}

QTabBar::tab:selected {
    background-color: #1f2937;
    color: #ffffff;
    border-color: #3b82f6;
}

QCheckBox {
    spacing: 7px;
    color: #d0dbe6;
}

QLabel#badgeReady {
    background-color: #123524;
    border: 1px solid #1e6b45;
    color: #6ee7b7;
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: 600;
    font-size: 12px;
}

QLabel#badgeError {
    background-color: #3b181e;
    border: 1px solid #882936;
    color: #fca5a5;
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: 600;
    font-size: 12px;
}

QLabel#badgeBusy {
    background-color: #1e2f4a;
    border: 1px solid #3b82f6;
    color: #93c5fd;
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: 600;
    font-size: 12px;
}

QScrollArea {
    background-color: transparent;
    border: none;
}

QScrollBar:vertical {
    background-color: #0d1218;
    width: 10px;
    border-radius: 5px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background-color: #303c4d;
    min-height: 24px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background-color: #4b5e77;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""
