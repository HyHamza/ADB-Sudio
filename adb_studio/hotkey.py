"""System-wide global hotkey support on Windows via Win32 RegisterHotKey."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_SPECIAL_VK: dict[str, int] = {
    "SPACE": 0x20,
    "TAB": 0x09,
    "RETURN": 0x0D,
    "ENTER": 0x0D,
    "ESC": 0x1B,
    "ESCAPE": 0x1B,
    "BACKSPACE": 0x08,
    "DELETE": 0x2E,
    "DEL": 0x2E,
    "INSERT": 0x2D,
    "INS": 0x2D,
    "HOME": 0x24,
    "END": 0x23,
    "PGUP": 0x21,
    "PAGEUP": 0x21,
    "PGDOWN": 0x22,
    "PAGEDOWN": 0x22,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "PRINTSCREEN": 0x2C,
    "PRINT": 0x2C,
    "SNAPSHOT": 0x2C,
    "PAUSE": 0x13,
}
for _i in range(1, 25):
    _SPECIAL_VK[f"F{_i}"] = 0x6F + _i


def parse_shortcut_to_win32(shortcut: str) -> tuple[int, int] | None:
    """Parse a Qt-style shortcut string (e.g. 'Ctrl+Alt+S') into (win32_mods, vk_code)."""
    cleaned = shortcut.strip()
    if not cleaned:
        return None
    parts = [p.strip().upper() for p in cleaned.split("+") if p.strip()]
    if not parts:
        return None

    mods = MOD_NOREPEAT
    key_token: str | None = None
    for part in parts:
        if part in {"CTRL", "CONTROL"}:
            mods |= MOD_CONTROL
        elif part == "ALT":
            mods |= MOD_ALT
        elif part == "SHIFT":
            mods |= MOD_SHIFT
        elif part in {"WIN", "META", "SUPER"}:
            mods |= MOD_WIN
        else:
            key_token = part

    if not key_token:
        return None

    if key_token in _SPECIAL_VK:
        return mods, _SPECIAL_VK[key_token]
    if len(key_token) == 1 and ("A" <= key_token <= "Z" or "0" <= key_token <= "9"):
        return mods, ord(key_token)
    return None


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
    ]


class _HotkeyEventFilter(QAbstractNativeEventFilter):
    """Native Windows event filter that catches WM_HOTKEY."""

    def __init__(self, hotkey_id: int, callback: Callable[[], None]) -> None:
        super().__init__()
        self._hotkey_id = hotkey_id
        self._callback = callback

    def nativeEventFilter(self, event_type, message):  # type: ignore[override]
        if sys.platform == "win32" and bytes(event_type) == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
            if msg.message == WM_HOTKEY and msg.wParam == self._hotkey_id:
                self._callback()
        return False, 0


class GlobalHotkeyManager(QObject):
    """Registers and listens for a single system-wide screenshot hotkey on Windows."""

    triggered = Signal()

    def __init__(self, app, hotkey_id: int = 0xADB1) -> None:
        super().__init__(app)
        self._app = app
        self._hotkey_id = hotkey_id
        self._registered = False
        self._filter = _HotkeyEventFilter(hotkey_id, self.triggered.emit)
        if sys.platform == "win32":
            self._app.installNativeEventFilter(self._filter)

    def register(self, shortcut: str) -> tuple[bool, str]:
        """Unregister any existing hotkey and register `shortcut` system-wide."""
        self.unregister()
        if not shortcut.strip():
            return True, "Global hotkey disabled."
        parsed = parse_shortcut_to_win32(shortcut)
        if parsed is None:
            return False, f"Unsupported shortcut format: '{shortcut}'"
        if sys.platform != "win32":
            return False, "Global hotkeys are only supported on Windows."

        mods, vk = parsed
        ok = bool(ctypes.windll.user32.RegisterHotKey(None, self._hotkey_id, mods, vk))
        if ok:
            self._registered = True
            return True, f"Global hotkey active: {shortcut}"
        return False, f"Could not register '{shortcut}' (may be in use by another app)."

    def unregister(self) -> None:
        """Unregister the active global hotkey if registered."""
        if self._registered and sys.platform == "win32":
            ctypes.windll.user32.UnregisterHotKey(None, self._hotkey_id)
        self._registered = False
