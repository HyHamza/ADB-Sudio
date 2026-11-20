"""Pure-Python ADB subprocess client for device management and command execution."""

from __future__ import annotations

import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from adb_studio.models import CommandResult, DeviceInfo

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def parse_devices_output(output: str) -> list[DeviceInfo]:
    """Parse `adb devices -l` output into a list of DeviceInfo objects."""
    devices: list[DeviceInfo] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("List of devices", "*")):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial = parts[0]
        state = parts[1]
        meta: dict[str, str] = {}
        for token in parts[2:]:
            if ":" in token:
                key, val = token.split(":", 1)
                meta[key] = val
        devices.append(
            DeviceInfo(
                serial=serial,
                state=state,
                model=meta.get("model", ""),
                product=meta.get("product", ""),
                device_code=meta.get("device", ""),
                transport_id=meta.get("transport_id", ""),
            )
        )
    return devices


def _escape_adb_input_text(text: str) -> str:
    """Escape text for `adb shell input text`."""
    # ADB `input text` treats %s as space and requires shell escaping for special chars.
    replacements = {
        " ": "%s",
        "&": r"\&",
        "<": r"\<",
        ">": r"\>",
        "|": r"\|",
        ";": r"\;",
        "(": r"\(",
        ")": r"\)",
        "$": r"\$",
        "`": r"\`",
        '"': r"\"",
        "'": r"\'",
    }
    out = []
    for ch in text:
        out.append(replacements.get(ch, ch))
    return "".join(out)


class AdbClient:
    """Thread-safe wrapper around the `adb` CLI binary."""

    def __init__(self, adb_path: str = "adb") -> None:
        self.adb_path = adb_path or "adb"

    def _build_cmd(self, args: list[str], serial: str | None = None) -> list[str]:
        cmd = [self.adb_path]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(args)
        return cmd

    def run(
        self,
        args: list[str],
        serial: str | None = None,
        timeout: float = 30.0,
    ) -> CommandResult:
        """Execute a text-mode ADB command and return a CommandResult."""
        cmd = self._build_cmd(args, serial=serial)
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
                creationflags=_CREATION_FLAGS,
            )
            elapsed = (time.perf_counter() - start) * 1000.0
            return CommandResult(
                command=cmd,
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                duration_ms=elapsed,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = (time.perf_counter() - start) * 1000.0
            stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return CommandResult(
                command=cmd,
                returncode=-1,
                stdout=stdout,
                stderr=stderr or f"Command timed out after {timeout:.0f}s.",
                duration_ms=elapsed,
                timed_out=True,
            )
        except FileNotFoundError:
            elapsed = (time.perf_counter() - start) * 1000.0
            return CommandResult(
                command=cmd,
                returncode=-1,
                stderr=f"ADB executable not found: '{self.adb_path}'. Set a valid adb.exe path in settings.",
                duration_ms=elapsed,
            )
        except OSError as exc:
            elapsed = (time.perf_counter() - start) * 1000.0
            return CommandResult(
                command=cmd,
                returncode=-1,
                stderr=str(exc),
                duration_ms=elapsed,
            )

    def run_binary(
        self,
        args: list[str],
        serial: str | None = None,
        timeout: float = 30.0,
    ) -> tuple[bytes, CommandResult]:
        """Execute an ADB command capturing raw stdout bytes (used for screencap)."""
        cmd = self._build_cmd(args, serial=serial)
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=False,
                timeout=timeout,
                check=False,
                creationflags=_CREATION_FLAGS,
            )
            elapsed = (time.perf_counter() - start) * 1000.0
            stderr_text = proc.stderr.decode("utf-8", errors="replace")
            return proc.stdout, CommandResult(
                command=cmd,
                returncode=proc.returncode,
                stdout=f"<{len(proc.stdout)} bytes>",
                stderr=stderr_text,
                duration_ms=elapsed,
            )
        except subprocess.TimeoutExpired:
            elapsed = (time.perf_counter() - start) * 1000.0
            return b"", CommandResult(
                command=cmd,
                returncode=-1,
                stderr=f"Command timed out after {timeout:.0f}s.",
                duration_ms=elapsed,
                timed_out=True,
            )
        except FileNotFoundError:
            elapsed = (time.perf_counter() - start) * 1000.0
            return b"", CommandResult(
                command=cmd,
                returncode=-1,
                stderr=f"ADB executable not found: '{self.adb_path}'.",
                duration_ms=elapsed,
            )
        except OSError as exc:
            elapsed = (time.perf_counter() - start) * 1000.0
            return b"", CommandResult(
                command=cmd,
                returncode=-1,
                stderr=str(exc),
                duration_ms=elapsed,
            )

    # ------------------------------------------------------------------
    # Server & Device Discovery
    # ------------------------------------------------------------------

    def check_version(self) -> CommandResult:
        return self.run(["version"], timeout=10.0)

    def list_devices(self) -> tuple[list[DeviceInfo], CommandResult]:
        res = self.run(["devices", "-l"], timeout=10.0)
        if not res.ok:
            return [], res
        return parse_devices_output(res.stdout), res

    def start_server(self) -> CommandResult:
        return self.run(["start-server"], timeout=15.0)

    def kill_server(self) -> CommandResult:
        return self.run(["kill-server"], timeout=10.0)

    # ------------------------------------------------------------------
    # Screenshot & Screen Recording
    # ------------------------------------------------------------------

    def take_screenshot(
        self,
        serial: str,
        save_dir: str | Path,
        prefix: str = "adb_screenshot",
        filename: str | None = None,
    ) -> tuple[Path | None, CommandResult]:
        """Capture device screenshot as PNG, save to `save_dir`, and return its Path."""
        target_dir = Path(save_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        if not filename:
            stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = f"{prefix}_{stamp}.png"
        out_path = target_dir / filename

        # Primary fast path: binary exec-out
        raw_bytes, res = self.run_binary(["exec-out", "screencap", "-p"], serial=serial, timeout=20.0)
        if res.ok and raw_bytes.startswith(PNG_SIGNATURE):
            out_path.write_bytes(raw_bytes)
            res.stdout = f"Saved screenshot to {out_path} ({len(raw_bytes):,} bytes)"
            res.extra["screenshot_path"] = str(out_path)
            return out_path, res

        # Fallback path for older Android builds where exec-out mangles or fails
        remote_tmp = "/sdcard/__adb_studio_tmp.png"
        cap_res = self.run(["shell", "screencap", "-p", remote_tmp], serial=serial, timeout=20.0)
        if not cap_res.ok:
            return None, cap_res
        pull_res = self.run(["pull", remote_tmp, str(out_path)], serial=serial, timeout=20.0)
        self.run(["shell", "rm", "-f", remote_tmp], serial=serial, timeout=10.0)

        if pull_res.ok and out_path.exists() and out_path.read_bytes().startswith(PNG_SIGNATURE):
            pull_res.extra["screenshot_path"] = str(out_path)
            return out_path, pull_res

        return None, CommandResult(
            command=res.command,
            returncode=-1,
            stderr=res.stderr or pull_res.stderr or "Failed to capture a valid PNG screenshot.",
            duration_ms=res.duration_ms,
        )

    def has_screenrecord(self, serial: str) -> bool:
        """Return True if the device has an accessible `screenrecord` binary."""
        res = self.run(
            ["shell", "command -v screenrecord >/dev/null 2>&1 && echo YES || echo NO"],
            serial=serial,
            timeout=10.0,
        )
        return res.ok and "YES" in res.stdout

    def record_screen(
        self,
        serial: str,
        save_dir: str | Path,
        duration_seconds: int = 15,
    ) -> tuple[Path | None, CommandResult]:
        """Record device screen for `duration_seconds` and pull MP4 to `save_dir`."""
        duration = max(1, min(int(duration_seconds), 180))
        target_dir = Path(save_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        out_path = target_dir / f"adb_record_{stamp}.mp4"
        remote_tmp = "/sdcard/__adb_studio_rec.mp4"

        rec_res = self.run(
            ["shell", "screenrecord", "--time-limit", str(duration), remote_tmp],
            serial=serial,
            timeout=float(duration + 20),
        )
        if not rec_res.ok:
            return None, rec_res

        pull_res = self.run(["pull", remote_tmp, str(out_path)], serial=serial, timeout=60.0)
        self.run(["shell", "rm", "-f", remote_tmp], serial=serial, timeout=10.0)
        if pull_res.ok and out_path.exists():
            pull_res.extra["recording_path"] = str(out_path)
            return out_path, pull_res
        return None, pull_res

    # ------------------------------------------------------------------
    # Device Info, Hardware Keys & Quick Controls
    # ------------------------------------------------------------------

    def get_device_summary(self, serial: str) -> CommandResult:
        script = (
            "echo \"Manufacturer: $(getprop ro.product.manufacturer)\"; "
            "echo \"Model: $(getprop ro.product.model)\"; "
            "echo \"Brand: $(getprop ro.product.brand)\"; "
            "echo \"Android: $(getprop ro.build.version.release) (SDK $(getprop ro.build.version.sdk))\"; "
            "echo \"ABI: $(getprop ro.product.cpu.abi)\"; "
            "echo \"Build: $(getprop ro.build.display.id)\"; "
            "wm size; wm density"
        )
        return self.run(["shell", script], serial=serial, timeout=15.0)

    def get_battery_info(self, serial: str) -> CommandResult:
        return self.run(["shell", "dumpsys", "battery"], serial=serial, timeout=15.0)

    def get_network_info(self, serial: str) -> CommandResult:
        return self.run(
            ["shell", "ip -f inet addr show | grep -E 'inet |^[0-9]+:'"],
            serial=serial,
            timeout=15.0,
        )

    def send_keyevent(self, serial: str, keycode: str) -> CommandResult:
        return self.run(["shell", "input", "keyevent", keycode], serial=serial, timeout=10.0)

    def send_text(self, serial: str, text: str) -> CommandResult:
        escaped = _escape_adb_input_text(text)
        return self.run(["shell", "input", "text", escaped], serial=serial, timeout=10.0)

    def open_url(self, serial: str, url: str) -> CommandResult:
        return self.run(
            ["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url],
            serial=serial,
            timeout=15.0,
        )

    def reboot(self, serial: str, mode: str = "") -> CommandResult:
        args = ["reboot"]
        if mode:
            args.append(mode)
        return self.run(args, serial=serial, timeout=15.0)

    def set_show_touches(self, serial: str, enabled: bool) -> CommandResult:
        val = "1" if enabled else "0"
        return self.run(
            ["shell", "settings", "put", "system", "show_touches", val],
            serial=serial,
            timeout=10.0,
        )

    def set_layout_bounds(self, serial: str, enabled: bool) -> CommandResult:
        val = "true" if enabled else "false"
        return self.run(
            ["shell", "setprop", "debug.layout", val],
            serial=serial,
            timeout=10.0,
        )

    def set_stay_awake(self, serial: str, enabled: bool) -> CommandResult:
        val = "true" if enabled else "false"
        return self.run(
            ["shell", "svc", "power", "stayon", val],
            serial=serial,
            timeout=10.0,
        )

    def set_screen_size(self, serial: str, size: str) -> CommandResult:
        arg = "reset" if size.strip().lower() == "reset" else size.strip()
        return self.run(["shell", "wm", "size", arg], serial=serial, timeout=10.0)

    def set_screen_density(self, serial: str, density: str) -> CommandResult:
        arg = "reset" if density.strip().lower() == "reset" else density.strip()
        return self.run(["shell", "wm", "density", arg], serial=serial, timeout=10.0)

    # ------------------------------------------------------------------
    # Apps / Packages
    # ------------------------------------------------------------------

    def list_packages(self, serial: str, mode: str = "third_party") -> tuple[list[str], CommandResult]:
        args = ["shell", "pm", "list", "packages"]
        if mode == "third_party":
            args.append("-3")
        elif mode == "system":
            args.append("-s")
        res = self.run(args, serial=serial, timeout=20.0)
        if not res.ok:
            return [], res
        pkgs = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                pkgs.append(line[len("package:"):])
        pkgs.sort()
        return pkgs, res

    def install_apk(self, serial: str, apk_path: str | Path, replace: bool = True) -> CommandResult:
        args = ["install"]
        if replace:
            args.append("-r")
        args.append(str(apk_path))
        return self.run(args, serial=serial, timeout=120.0)

    def uninstall_package(self, serial: str, package: str, keep_data: bool = False) -> CommandResult:
        args = ["uninstall"]
        if keep_data:
            args.append("-k")
        args.append(package)
        return self.run(args, serial=serial, timeout=30.0)

    def launch_package(self, serial: str, package: str) -> CommandResult:
        return self.run(
            ["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"],
            serial=serial,
            timeout=15.0,
        )

    def force_stop_package(self, serial: str, package: str) -> CommandResult:
        return self.run(["shell", "am", "force-stop", package], serial=serial, timeout=15.0)

    def clear_package_data(self, serial: str, package: str) -> CommandResult:
        return self.run(["shell", "pm", "clear", package], serial=serial, timeout=15.0)

    def pull_apk(self, serial: str, package: str, dest_dir: str | Path) -> CommandResult:
        path_res = self.run(["shell", "pm", "path", package], serial=serial, timeout=15.0)
        if not path_res.ok:
            return path_res
        apk_remote = ""
        for line in path_res.stdout.splitlines():
            if line.startswith("package:"):
                apk_remote = line[len("package:"):].strip()
                break
        if not apk_remote:
            return CommandResult(
                command=path_res.command,
                returncode=-1,
                stderr=f"Could not resolve APK path for {package}.",
            )
        dest_path = Path(dest_dir) / f"{package}.apk"
        return self.run(["pull", apk_remote, str(dest_path)], serial=serial, timeout=60.0)

    # ------------------------------------------------------------------
    # File Transfer
    # ------------------------------------------------------------------

    def push_file(self, serial: str, local_path: str | Path, remote_path: str) -> CommandResult:
        return self.run(["push", str(local_path), remote_path], serial=serial, timeout=120.0)

    def pull_file(self, serial: str, remote_path: str, local_path: str | Path) -> CommandResult:
        return self.run(["pull", remote_path, str(local_path)], serial=serial, timeout=120.0)

    # ------------------------------------------------------------------
    # Wireless ADB
    # ------------------------------------------------------------------

    def enable_tcpip(self, serial: str, port: int = 5555) -> CommandResult:
        return self.run(["tcpip", str(port)], serial=serial, timeout=15.0)

    def connect_wireless(self, target: str) -> CommandResult:
        return self.run(["connect", target.strip()], timeout=15.0)

    def disconnect_wireless(self, target: str = "") -> CommandResult:
        args = ["disconnect"]
        if target.strip():
            args.append(target.strip())
        return self.run(args, timeout=10.0)

    def pair_wireless(self, target: str, code: str) -> CommandResult:
        return self.run(["pair", target.strip(), code.strip()], timeout=20.0)

    # ------------------------------------------------------------------
    # Logcat & Custom Shell
    # ------------------------------------------------------------------

    def dump_logcat(self, serial: str, lines: int = 400) -> CommandResult:
        return self.run(["logcat", "-d", "-t", str(lines)], serial=serial, timeout=20.0)

    def clear_logcat(self, serial: str) -> CommandResult:
        return self.run(["logcat", "-c"], serial=serial, timeout=10.0)

    def run_custom(self, serial: str | None, raw_command: str) -> CommandResult:
        tokens = shlex.split(raw_command.strip(), posix=False)
        if not tokens:
            return CommandResult(command=[], returncode=-1, stderr="Empty command.")
        if tokens[0].lower() in {"adb", "adb.exe"}:
            tokens = tokens[1:]
        if not tokens:
            return CommandResult(command=[], returncode=-1, stderr="No ADB arguments provided.")
        return self.run(tokens, serial=serial, timeout=30.0)
