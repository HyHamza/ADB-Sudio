# Architecture Overview

ADB Studio separates ADB process execution, background Qt threading, Windows OS integrations, and UI rendering into distinct modules under `adb_studio/`.

## Core Modules

### `adb_studio/adb_client.py` & `adb_studio/models.py`
- `ADBClient` wraps `adb` CLI invocations via `subprocess.run` and returns structured `CommandResult` objects (`command`, `returncode`, `stdout`, `stderr`, `duration_ms`, `timed_out`).
- Device discovery parses `adb devices -l` into `DeviceInfo` instances (`serial`, `state`, `model`, `product`, `device_code`, `transport_id`).
- All unit tests in `tests/test_adb_client.py` mock subprocess calls to verify parsing, command construction, and timeout/error handling without requiring a connected device.

### `adb_studio/workers.py`
- Keeps long-running ADB commands, APK operations, file transfers, and captures off the Qt main thread so the UI stays responsive.

### `adb_studio/recorder.py`
`ScreenRecorderSession` implements a 3-tier recording strategy so recording works across different Android versions and setups:
1. **`scrcpy` backend (`_run_scrcpy`)**: Uses `scrcpy --no-window --no-audio` (or configured path) when available for reliable, low-overhead `.mp4` capture.
2. **Native `screenrecord` backend (`_run_native`)**: Runs `adb shell screenrecord` on-device and pulls the resulting `.mp4` when stopped.
3. **Fallback `screencap` backend (`_run_fallback_screencap`)**: Captures sequential PNG frames via `adb exec-out screencap -p` and stitches them into an `.mp4` using OpenCV (`cv2`) and NumPy when neither `scrcpy` nor native `screenrecord` is usable.

### `adb_studio/hotkey.py`
- `GlobalHotkeyManager` installs a `QAbstractNativeEventFilter` on the `QApplication` and calls Win32 `RegisterHotKey` / `UnregisterHotKey` via `ctypes.windll.user32`.
- Parses Qt-style shortcut strings (e.g., `Ctrl+Alt+S`) into Win32 modifier flags and virtual key codes, emitting a Qt `Signal` (`triggered`) when `WM_HOTKEY` is received.

### `adb_studio/startup.py` & `adb_studio/config.py`
- `AppConfig` loads and saves JSON preferences to `~/.adb_studio/config.json`, including `adb_path`, `scrcpy_path`, `screenshot_dir`, `global_hotkey`, tray behavior, and the last 10 wireless `IP:port` targets.
- `startup.py` manages Windows login auto-startup by writing or deleting the `ADBStudio` entry under `HKCU\Software\Microsoft\CurrentVersion\Run` (launching with `--minimized` when enabled).

### `adb_studio/ui/`
- `main_window.py`: Houses the device sidebar, 6 feature tabs (`Controls & Keys`, `Device & Screen`, `Apps (APK Manager)`, `Files & Wireless ADB`, `Shell & Logcat`, `Settings`), system tray icon, and command output log.
- `hud_toast.py`: Lightweight frameless overlay widget shown after global-hotkey captures.
- `styles.py`: Application-wide dark stylesheet (`DARK_STYLESHEET`).
