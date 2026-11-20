"""Data models for ADB devices and command execution results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DeviceInfo:
    """Represents a single connected Android device reported by `adb devices -l`."""

    serial: str
    state: str
    model: str = ""
    product: str = ""
    device_code: str = ""
    transport_id: str = ""

    @property
    def is_ready(self) -> bool:
        """Return True if the device is online and authorized for ADB commands."""
        return self.state == "device"

    @property
    def is_wireless(self) -> bool:
        """Return True if the serial looks like an IP:port wireless target."""
        return ":" in self.serial

    @property
    def display_name(self) -> str:
        """Human-friendly label for the UI list."""
        name = self.model.replace("_", " ") if self.model else (self.device_code or "Android Device")
        return f"{name} ({self.serial})"


@dataclass(slots=True)
class CommandResult:
    """Result of executing an ADB command."""

    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    timed_out: bool = False
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Return True when the command exited cleanly without timeout."""
        return self.returncode == 0 and not self.timed_out

    @property
    def combined_output(self) -> str:
        """Return non-empty stdout and stderr joined cleanly."""
        parts = [p.strip() for p in (self.stdout, self.stderr) if p and p.strip()]
        return "\n".join(parts)
