"""Unit tests for ADB Studio core client, config, and UI smoke checks."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from adb_studio.adb_client import PNG_SIGNATURE, AdbClient, parse_devices_output
from adb_studio.config import AppConfig
from adb_studio.hotkey import MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, MOD_SHIFT, parse_shortcut_to_win32
from adb_studio.models import CommandResult
from adb_studio.recorder import ScreenRecorderSession
from adb_studio.startup import build_startup_command
from adb_studio.ui.hud_toast import ScreenshotHudToast
from adb_studio.ui.main_window import MainWindow


def test_parse_devices_output_handles_multiple_states() -> None:
    sample = """* daemon not running; starting now at tcp:5037
* daemon started successfully
List of devices attached
R58M12345AB\tdevice product:beyond1q model:SM_G973F device:beyond1 transport_id:2
192.168.1.50:5555\tdevice product:raven model:Pixel_6_Pro device:raven transport_id:4
ABCD9999\tunauthorized transport_id:5
EFGH0000\toffline

"""
    devices = parse_devices_output(sample)
    assert len(devices) == 4

    assert devices[0].serial == "R58M12345AB"
    assert devices[0].is_ready is True
    assert devices[0].is_wireless is False
    assert devices[0].model == "SM_G973F"
    assert "SM G973F" in devices[0].display_name

    assert devices[1].serial == "192.168.1.50:5555"
    assert devices[1].is_ready is True
    assert devices[1].is_wireless is True

    assert devices[2].state == "unauthorized"
    assert devices[2].is_ready is False

    assert devices[3].state == "offline"
    assert devices[3].is_ready is False


def test_config_roundtrip_and_corrupt_fallback(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.json"
    cfg = AppConfig(
        adb_path="C:/platform-tools/adb.exe",
        screenshot_dir=str(tmp_path / "shots"),
        auto_copy_clipboard=False,
    )
    cfg.add_wireless_target("192.168.1.10:5555")
    cfg.add_wireless_target("192.168.1.20:5555")
    cfg.add_wireless_target("192.168.1.10:5555")
    cfg.save(cfg_file)

    loaded = AppConfig.load(cfg_file)
    assert loaded.adb_path == "C:/platform-tools/adb.exe"
    assert loaded.screenshot_dir == str(tmp_path / "shots")
    assert loaded.auto_copy_clipboard is False
    assert loaded.wireless_history == ["192.168.1.10:5555", "192.168.1.20:5555"]

    cfg_file.write_text("{not valid json", encoding="utf-8")
    fallback = AppConfig.load(cfg_file)
    assert fallback.auto_copy_clipboard is True


def test_take_screenshot_exec_out_success(tmp_path: Path) -> None:
    client = AdbClient("adb")
    fake_png = PNG_SIGNATURE + b"\x00\x00\x00\rIHDRfake_png_payload"

    mock_proc = MagicMock(returncode=0, stdout=fake_png, stderr=b"")
    with patch("adb_studio.adb_client.subprocess.run", return_value=mock_proc) as run_mock:
        out_path, res = client.take_screenshot("SERIAL123", tmp_path, filename="test_shot.png")

    assert res.ok is True
    assert out_path == tmp_path / "test_shot.png"
    assert out_path.read_bytes() == fake_png
    called_cmd = run_mock.call_args.args[0]
    assert called_cmd == ["adb", "-s", "SERIAL123", "exec-out", "screencap", "-p"]


def test_take_screenshot_falls_back_to_pull(tmp_path: Path) -> None:
    client = AdbClient("adb")
    fake_png = PNG_SIGNATURE + b"fallback_png_data"

    def fake_run(cmd, **kwargs):
        if "exec-out" in cmd:
            return MagicMock(returncode=1, stdout=b"", stderr=b"exec-out unsupported")
        if cmd[-2:] == ["screencap", "-p"] or "/sdcard/__adb_studio_tmp.png" in cmd and "shell" in cmd and "rm" not in cmd:
            return MagicMock(returncode=0, stdout="", stderr="")
        if "pull" in cmd:
            Path(cmd[-1]).write_bytes(fake_png)
            return MagicMock(returncode=0, stdout="1 file pulled", stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("adb_studio.adb_client.subprocess.run", side_effect=fake_run):
        out_path, res = client.take_screenshot("SERIAL123", tmp_path, filename="fallback.png")

    assert res.ok is True
    assert out_path == tmp_path / "fallback.png"
    assert out_path.read_bytes() == fake_png


def test_run_custom_strips_adb_prefix() -> None:
    client = AdbClient("adb")
    mock_proc = MagicMock(returncode=0, stdout="14\n", stderr="")
    with patch("adb_studio.adb_client.subprocess.run", return_value=mock_proc) as run_mock:
        res = client.run_custom("DEV1", "adb shell getprop ro.build.version.release")

    assert res.ok is True
    assert res.stdout.strip() == "14"
    assert run_mock.call_args.args[0] == [
        "adb",
        "-s",
        "DEV1",
        "shell",
        "getprop",
        "ro.build.version.release",
    ]


def test_mainwindow_smoke_and_clipboard_copy(tmp_path: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])

    cfg = AppConfig(screenshot_dir=str(tmp_path), auto_refresh_devices=False)
    # Create a real PNG image to verify QImage + QClipboard integration
    png_path = tmp_path / "sample.png"
    Image.new("RGB", (32, 32), color=(37, 99, 235)).save(png_path)

    with patch.object(MainWindow, "_check_adb_status"), patch.object(MainWindow, "refresh_devices"):
        win = MainWindow(config=cfg, config_path=tmp_path / "ui_config.json")
        win._apply_device_list(
            parse_devices_output(
                "List of devices attached\nUSB123\tdevice model:Pixel_8 transport_id:1\n"
            )
        )
        assert win._selected_serial == "USB123"
        assert win.screenshot_btn.isEnabled() is True

        copied = win._copy_image_to_clipboard(png_path)
        assert copied is True
        clip_img: QImage = app.clipboard().image()
        assert not clip_img.isNull()
        assert clip_img.width() == 32
        win._force_quit = True
        win.close()


def test_screen_recorder_fallback_creates_mp4(tmp_path: Path) -> None:
    import io

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color=(16, 185, 129)).save(buf, format="PNG")
    png_bytes = buf.getvalue()

    client = AdbClient("adb")
    session = ScreenRecorderSession(client, "EPHUT20521002591", tmp_path, max_seconds=5)

    calls = 0

    def fake_run_binary(args, serial=None, timeout=30.0):
        nonlocal calls
        calls += 1
        if calls >= 3:
            session.request_stop()
        return png_bytes, CommandResult(command=["adb", *args], returncode=0)

    with (
        patch.object(client, "has_screenrecord", return_value=False),
        patch.object(client, "run_binary", side_effect=fake_run_binary),
    ):
        mode = session.start()
        assert mode == "fallback"
        outcome = session.run_until_stopped()

    assert outcome.result.ok is True
    assert outcome.mode == "fallback"
    assert outcome.frames_captured >= 2
    assert outcome.output_path is not None
    assert outcome.output_path.exists()
    assert outcome.output_path.stat().st_size > 0


def test_screen_recorder_prefers_scrcpy_when_available(tmp_path: Path) -> None:
    fake_scrcpy = tmp_path / "scrcpy.exe"
    fake_scrcpy.write_bytes(b"MZ")

    client = AdbClient("adb")
    session = ScreenRecorderSession(
        client,
        "EPHUT20521002591",
        tmp_path,
        max_seconds=10,
        scrcpy_path=str(fake_scrcpy),
    )

    def fake_popen(cmd, **kwargs):
        rec_arg = next(a for a in cmd if a.startswith("--record="))
        Path(rec_arg.split("=", 1)[1]).write_bytes(b"\x00\x00\x00\x18ftypmp42")
        proc = MagicMock()
        proc.poll.return_value = 0
        proc.returncode = 0
        proc.communicate.return_value = ("", "")
        return proc

    with patch("adb_studio.recorder.subprocess.Popen", side_effect=fake_popen):
        mode = session.start()
        assert mode == "scrcpy"
        outcome = session.run_until_stopped()

    assert outcome.result.ok is True
    assert outcome.mode == "scrcpy"
    assert outcome.output_path is not None
    assert outcome.output_path.exists()


def test_screen_recorder_scrcpy_stop_kills_remote_server(tmp_path: Path) -> None:
    fake_scrcpy = tmp_path / "scrcpy.exe"
    fake_scrcpy.write_bytes(b"MZ")

    client = AdbClient("adb")
    session = ScreenRecorderSession(
        client,
        "EPHUT20521002591",
        tmp_path,
        max_seconds=30,
        scrcpy_path=str(fake_scrcpy),
    )

    stopped = False

    def fake_popen(cmd, **kwargs):
        rec_arg = next(a for a in cmd if a.startswith("--record="))
        Path(rec_arg.split("=", 1)[1]).write_bytes(b"\x00\x00\x00\x18ftypmp42")
        proc = MagicMock()
        proc.poll.side_effect = lambda: 0 if stopped else None
        proc.returncode = 0
        proc.communicate.return_value = ("", "")
        return proc

    def fake_run(args, serial=None, timeout=30.0):
        nonlocal stopped
        if "pkill" in " ".join(args):
            stopped = True
        return CommandResult(command=["adb", *args], returncode=0)

    with (
        patch("adb_studio.recorder.subprocess.Popen", side_effect=fake_popen),
        patch.object(client, "run", side_effect=fake_run) as run_mock,
    ):
        session.start()
        session.request_stop()
        outcome = session.run_until_stopped()

    assert outcome.result.ok is True
    assert any("com.genymobile.scrcpy.Server" in " ".join(c.args[0]) for c in run_mock.call_args_list)


def test_parse_shortcut_to_win32() -> None:
    parsed = parse_shortcut_to_win32("Ctrl+Alt+S")
    assert parsed == (MOD_NOREPEAT | MOD_CONTROL | MOD_ALT, ord("S"))

    parsed_fn = parse_shortcut_to_win32("Ctrl+Shift+F9")
    assert parsed_fn == (MOD_NOREPEAT | MOD_CONTROL | MOD_SHIFT, 0x78)

    assert parse_shortcut_to_win32("") is None
    assert parse_shortcut_to_win32("Ctrl+") is None


def test_build_startup_command(tmp_path: Path) -> None:
    script = tmp_path / "main.py"
    script.write_text("print('ok')", encoding="utf-8")
    cmd_min = build_startup_command(script, start_minimized=True)
    assert str(script.resolve()) in cmd_min
    assert cmd_min.endswith(" --minimized")

    cmd_vis = build_startup_command(script, start_minimized=False)
    assert not cmd_vis.endswith(" --minimized")


def test_screenshot_hud_toast_transitions() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app = QApplication.instance() or QApplication([])
    toast = ScreenshotHudToast()
    toast.show_capturing()
    assert toast._label.text() == "Taking screenshot..."
    toast.show_captured(copied=True)
    assert toast._label.text() == "Captured & Copied to Clipboard"
    toast.show_error("No ready ADB device selected")
    assert toast._label.text() == "No ready ADB device selected"
    toast.close()





