"""Persistent configuration management for ADB Studio."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".adb_studio" / "config.json"


def default_screenshot_dir() -> str:
    """Return the default folder path for saving screenshots."""
    return str(Path.home() / "Pictures" / "ADB_Screenshots")


def resolve_default_adb() -> str:
    """Locate `adb` on PATH if available, otherwise return 'adb'."""
    return shutil.which("adb") or "adb"


def resolve_default_scrcpy() -> str:
    """Locate `scrcpy` on PATH or common Android SDK sibling folders."""
    found = shutil.which("scrcpy")
    if found:
        return found
    for candidate in (
        Path(r"C:\Android\Android\scrcpy\scrcpy.exe"),
        Path(r"C:\scrcpy\scrcpy.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    return ""


@dataclass
class AppConfig:
    """User preferences persisted between sessions."""

    adb_path: str = field(default_factory=resolve_default_adb)
    scrcpy_path: str = field(default_factory=resolve_default_scrcpy)
    screenshot_dir: str = field(default_factory=default_screenshot_dir)
    auto_copy_clipboard: bool = True
    screenshot_prefix: str = "adb_screenshot"
    auto_refresh_devices: bool = True
    global_hotkey: str = "Ctrl+Alt+S"
    run_in_background: bool = True
    start_minimized: bool = False
    wireless_history: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
        """Load configuration from disk, falling back to defaults on error."""
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return cls()
            defaults = cls()
            return cls(
                adb_path=str(raw.get("adb_path") or defaults.adb_path),
                scrcpy_path=str(raw.get("scrcpy_path") or defaults.scrcpy_path),
                screenshot_dir=str(raw.get("screenshot_dir") or defaults.screenshot_dir),
                auto_copy_clipboard=bool(raw.get("auto_copy_clipboard", True)),
                screenshot_prefix=str(raw.get("screenshot_prefix") or "adb_screenshot"),
                auto_refresh_devices=bool(raw.get("auto_refresh_devices", True)),
                global_hotkey=str(raw.get("global_hotkey", defaults.global_hotkey)),
                run_in_background=bool(raw.get("run_in_background", True)),
                start_minimized=bool(raw.get("start_minimized", False)),
                wireless_history=list(raw.get("wireless_history") or [])[:10],
            )
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self, path: Path = DEFAULT_CONFIG_PATH) -> None:
        """Persist configuration to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    def add_wireless_target(self, target: str) -> None:
        """Record a wireless IP:port target at the front of history."""
        cleaned = target.strip()
        if not cleaned:
            return
        self.wireless_history = [cleaned] + [t for t in self.wireless_history if t != cleaned]
        self.wireless_history = self.wireless_history[:10]
