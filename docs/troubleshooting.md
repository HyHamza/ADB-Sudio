# Troubleshooting

## `adb` not found / Device list is empty

- Verify `adb version` works in PowerShell.
- If `adb` is not on your system `PATH`, open the **Settings** tab in ADB Studio and point **ADB Path** directly to `adb.exe` (for example, `C:\platform-tools\adb.exe`).
- If a device shows as `UNAUTHORIZED`, unlock the phone screen and accept the **Allow USB debugging** prompt.

## Global hotkey (`Ctrl+Alt+S`) fails to register

- Win32 `RegisterHotKey` fails if another application already owns the same shortcut.
- Change the **Global Hotkey** in the **Settings** tab (for example, `Ctrl+Shift+S` or `Ctrl+Alt+P`) and save, or leave it blank to disable the global hotkey.

## Screen recording falls back to low-FPS capture

- ADB Studio prefers `scrcpy`, then `adb shell screenrecord`, and finally a `screencap` frame-stitcher.
- Some emulators or devices lack `screenrecord` support or restrict it; in that case the fallback `screencap` backend is used automatically, which has a lower frame rate.
- For smoother recordings without mirroring on screen, install `scrcpy` and ensure it is on `PATH` or set **Scrcpy Path** in **Settings**.

## Wireless ADB connection fails

- For legacy TCP/IP mode, connect via USB first, click **Enable TCP/IP (:5555)** in **Files & Wireless ADB**, then connect using `<device-ip>:5555`.
- For Android 11+ wireless debugging without USB, use **Wireless Pairing** with the IP, pairing port, and 6-digit pairing code shown on the device, then connect to the main debugging port.
