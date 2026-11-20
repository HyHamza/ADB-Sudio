# ADB Studio

A desktop GUI for **Android Debug Bridge (ADB)** built with Python and PySide6, focused on fast screenshot-to-clipboard capture, global hotkeys, screen recording, and day-to-day Android device management on Windows.

## Features

- **Device Manager**: Live list of USB and wireless ADB devices (`READY`, `UNAUTHORIZED`, `OFFLINE`), auto-refresh every 3 seconds, single-device selection, and ADB server start/kill controls.
- **Screenshot & Clipboard Workflow**:
  - One-click capture (`Ctrl+S`) or system-wide global hotkey (`Ctrl+Alt+S` by default, works while minimized to tray).
  - Auto-copies captured screenshots to the Windows clipboard for immediate `Ctrl+V` pasting.
  - Floating HUD toast notification on capture, live thumbnail preview, and configurable save directory/prefix.
- **Screen Recording (`.mp4`)**:
  - Uses `scrcpy` (no-mirroring recording) when available, falls back to native `adb shell screenrecord`, and uses an OpenCV `screencap` frame-stitcher if neither is supported on the device.
- **Controls & Keys**: Hardware/navigation keys (Home, Back, Recents, Power, Wake, Sleep, Volume, Enter, Menu), text input, URL launcher, developer toggles (Show Touches, Layout Bounds, Stay Awake), and reboot modes (System, Recovery, Bootloader, Fastboot).
- **Device & Screen Diagnostics**: Device summary, battery and network/IP info, and resolution/DPI overrides (`wm size` / `wm density`).
- **Apps (APK Manager)**: Filter 3rd-party/all/system packages with live search, install APKs, launch, force stop, clear data, pull APKs, and uninstall.
- **Files & Wireless ADB**: Push/pull files, enable TCP/IP (`:5555`), connect/disconnect Wi-Fi ADB with target history, and Android 11+ wireless pairing.
- **Shell & Logcat**: Custom ADB command runner, quick presets, logcat dump/clear/save, and a live command output log.
- **Background Tray & Startup**: Optional minimize-to-tray behavior (`--minimized`) and Windows login auto-start registration.

## Requirements

- **OS**: Windows 10/11 (core ADB features use cross-platform Qt/Python, while global hotkeys, AppUserModelID, and login auto-start use Win32 APIs).
- **Python**: 3.11 or newer.
- **Android Platform Tools**: `adb` available on `PATH`, or configured manually in **Settings**.
- **Optional**: `scrcpy` on `PATH` (or configured in **Settings**) for hardware-accelerated no-display recording.

## Quick Start

```powershell
git clone https://github.com/HyHamza/ADB-Sudio.git
cd ADB-Sudio
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

To start minimized in the system tray:

```powershell
python main.py --minimized
```

## Shortcuts

| Shortcut | Scope | Action |
| --- | --- | --- |
| `Ctrl+Alt+S` | System-wide (configurable) | Capture screenshot & copy to clipboard |
| `Ctrl+S` | App window | Capture screenshot |
| `F5` | App window | Refresh connected devices |

## Configuration

Settings are persisted as JSON at:

```text
%USERPROFILE%\.adb_studio\config.json
```

By default, screenshots are saved to `%USERPROFILE%\Pictures\ADB_Screenshots`.

## Project Structure

```text
ADB-Sudio/
├── main.py                  # Application entry point
├── adb_studio/
│   ├── adb_client.py        # ADB subprocess wrapper & output parsers
│   ├── branding.py          # App icon & Windows taskbar ID setup
│   ├── config.py            # JSON config persistence & tool discovery
│   ├── hotkey.py            # Win32 RegisterHotKey global shortcut listener
│   ├── models.py            # DeviceInfo and CommandResult dataclasses
│   ├── recorder.py          # 3-tier screen recording session manager
│   ├── startup.py           # Windows HKCU Run auto-startup helper
│   ├── workers.py           # Background task runner for Qt UI
│   └── ui/
│       ├── main_window.py   # Main tabbed interface & tray integration
│       ├── hud_toast.py     # Floating screenshot feedback toast
│       └── styles.py        # Dark theme QSS stylesheet
├── assets/                  # Application icons (.ico, .png)
├── docs/                    # Architecture, build, and troubleshooting docs
├── tests/                   # Unit tests for ADB client & parsers
├── ADBStudio.spec           # PyInstaller single-exe build spec
├── installer.iss            # Inno Setup Windows installer script
└── pyproject.toml           # Project metadata, ruff, and pytest config
```

## Documentation

- [Architecture Overview](docs/architecture.md)
- [Building & Packaging (EXE / Installer)](docs/building.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Contributing](CONTRIBUTING.md)

## License

[MIT](LICENSE)
