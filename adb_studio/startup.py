"""Windows auto-startup registration via HKCU Run registry key."""

from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY_PATH = r"Software\Microsoft\CurrentVersion\Run"
APP_RUN_NAME = "ADBStudio"


def resolve_pythonw_executable() -> str:
    """Return pythonw.exe next to sys.executable if available, else sys.executable."""
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(exe)


def build_startup_command(main_script: Path, start_minimized: bool = True) -> str:
    """Build the Windows Run registry command string for dev or frozen exe."""
    flag = " --minimized" if start_minimized else ""
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"{flag}'
    py_exe = resolve_pythonw_executable()
    return f'"{py_exe}" "{main_script.resolve()}"{flag}'


def is_autostart_enabled() -> bool:
    """Return True if ADBStudio is registered in HKCU Run."""
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_RUN_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool, main_script: Path, start_minimized: bool = True) -> tuple[bool, str]:
    """Enable or disable Windows login auto-startup for ADB Studio."""
    if sys.platform != "win32":
        return False, "Auto-startup is only supported on Windows."
    import winreg

    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY_PATH,
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_READ,
        ) as key:
            if enabled:
                cmd = build_startup_command(main_script, start_minimized=start_minimized)
                winreg.SetValueEx(key, APP_RUN_NAME, 0, winreg.REG_SZ, cmd)
                return True, "Auto-startup enabled for Windows login."
            try:
                winreg.DeleteValue(key, APP_RUN_NAME)
            except FileNotFoundError:
                pass
            return True, "Auto-startup disabled."
    except OSError as exc:
        return False, f"Failed to update Windows startup registry: {exc}"
