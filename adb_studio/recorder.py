"""Screen recording session supporting scrcpy (60 FPS), native `screenrecord`, and screencap fallback."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from adb_studio.adb_client import PNG_SIGNATURE, AdbClient
from adb_studio.models import CommandResult

_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_SCRCPY_FLAGS = (
    (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
    if sys.platform == "win32"
    else 0
)
_FALLBACK_FPS = 10.0


@dataclass(slots=True)
class RecordingOutcome:
    """Final result of a screen recording session."""

    output_path: Path | None
    mode: str  # "scrcpy" | "native" | "fallback"
    result: CommandResult
    frames_captured: int = 0


class ScreenRecorderSession:
    """Manages a start/stop ADB screen recording session on a single device."""

    def __init__(
        self,
        client: AdbClient,
        serial: str,
        save_dir: str | Path,
        max_seconds: int = 30,
        scrcpy_path: str = "",
    ) -> None:
        self.client = client
        self.serial = serial
        self.save_dir = Path(save_dir)
        self.max_seconds = max(3, min(int(max_seconds), 180))
        self.scrcpy_path = scrcpy_path.strip()

        self.mode: str = "scrcpy"
        self._stop_event = threading.Event()
        self._proc: subprocess.Popen[str] | None = None
        self._remote_tmp = "/sdcard/__adb_studio_rec.mp4"
        self._started_at: float = 0.0

    def start(self) -> str:
        """Detect best available recording mode ('scrcpy', 'native', or 'fallback')."""
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self._started_at = time.perf_counter()
        if self.scrcpy_path and Path(self.scrcpy_path).exists():
            self.mode = "scrcpy"
        elif self.client.has_screenrecord(self.serial):
            self.mode = "native"
        else:
            self.mode = "fallback"
        return self.mode

    def request_stop(self) -> None:
        """Signal the active recording process or loop to stop and finalize MP4."""
        self._stop_event.set()

    def run_until_stopped(self) -> RecordingOutcome:
        """Block in worker thread until stopped or max_seconds elapses, returning MP4 path."""
        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        out_path = self.save_dir / f"adb_record_{stamp}.mp4"
        if self.mode == "scrcpy":
            return self._run_scrcpy(out_path)
        if self.mode == "native":
            return self._run_native(out_path)
        return self._run_fallback_screencap(out_path)

    def _run_scrcpy(self, out_path: Path) -> RecordingOutcome:
        cmd = [
            self.scrcpy_path,
            "--serial",
            self.serial,
            "--no-window",
            "--no-audio",
            f"--time-limit={self.max_seconds}",
            f"--record={out_path}",
        ]
        env = os.environ.copy()
        adb_dir = str(Path(self.client.adb_path).parent)
        if Path(self.client.adb_path).is_file():
            env["ADB"] = self.client.adb_path
            env["PATH"] = f"{adb_dir}{os.pathsep}{env.get('PATH', '')}"

        start = time.perf_counter()
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                creationflags=_SCRCPY_FLAGS,
            )
            stopped_by_user = False
            while self._proc.poll() is None:
                if self._stop_event.wait(0.2):
                    stopped_by_user = True
                    break

            if stopped_by_user and self._proc.poll() is None:
                # Try signal first, then close the on-device scrcpy server so PC scrcpy flushes MP4 on EOF.
                try:
                    if sys.platform == "win32":
                        self._proc.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        self._proc.send_signal(signal.SIGINT)
                except OSError:
                    pass
                self.client.run(
                    ["shell", "pkill -2 -f com.genymobile.scrcpy.Server"],
                    serial=self.serial,
                    timeout=3.0,
                )

            try:
                stdout, stderr = self._proc.communicate(timeout=4.0)
            except subprocess.TimeoutExpired:
                self._proc.terminate()
                try:
                    stdout, stderr = self._proc.communicate(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    stdout, stderr = self._proc.communicate()

            elapsed = (time.perf_counter() - start) * 1000.0
            if out_path.exists() and out_path.stat().st_size > 0:
                return RecordingOutcome(
                    output_path=out_path,
                    mode="scrcpy",
                    result=CommandResult(
                        command=cmd,
                        returncode=0,
                        stdout=f"Recorded smooth MP4 via scrcpy to {out_path.name}",
                        stderr=stderr,
                        duration_ms=elapsed,
                    ),
                )

            return RecordingOutcome(
                output_path=None,
                mode="scrcpy",
                result=CommandResult(
                    command=cmd,
                    returncode=self._proc.returncode if self._proc.returncode is not None else -1,
                    stdout=stdout,
                    stderr=stderr or "scrcpy did not produce a recording file.",
                    duration_ms=elapsed,
                ),
            )
        except OSError as exc:
            return RecordingOutcome(
                output_path=None,
                mode="scrcpy",
                result=CommandResult(command=cmd, returncode=-1, stderr=str(exc)),
            )

    def _run_native(self, out_path: Path) -> RecordingOutcome:
        cmd = [
            self.client.adb_path,
            "-s",
            self.serial,
            "shell",
            "screenrecord",
            "--time-limit",
            str(self.max_seconds),
            self._remote_tmp,
        ]
        start = time.perf_counter()
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_CREATION_FLAGS,
            )
            stopped_by_user = False
            while self._proc.poll() is None:
                if self._stop_event.wait(0.2):
                    stopped_by_user = True
                    break

            if stopped_by_user and self._proc.poll() is None:
                self.client.run(
                    ["shell", "pkill -2 screenrecord || killall -2 screenrecord"],
                    serial=self.serial,
                    timeout=4.0,
                )

            try:
                stdout, stderr = self._proc.communicate(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                stdout, stderr = self._proc.communicate()

            pull_res = self.client.run(
                ["pull", self._remote_tmp, str(out_path)],
                serial=self.serial,
                timeout=60.0,
            )
            self.client.run(["shell", "rm", "-f", self._remote_tmp], serial=self.serial, timeout=10.0)
            elapsed = (time.perf_counter() - start) * 1000.0

            if pull_res.ok and out_path.exists():
                pull_res.duration_ms = elapsed
                return RecordingOutcome(output_path=out_path, mode="native", result=pull_res)

            return RecordingOutcome(
                output_path=None,
                mode="native",
                result=CommandResult(
                    command=cmd,
                    returncode=pull_res.returncode,
                    stdout=stdout,
                    stderr=pull_res.stderr or stderr,
                    duration_ms=elapsed,
                ),
            )
        except OSError as exc:
            return RecordingOutcome(
                output_path=None,
                mode="native",
                result=CommandResult(command=cmd, returncode=-1, stderr=str(exc)),
            )

    def _run_fallback_screencap(self, out_path: Path) -> RecordingOutcome:
        """Capture PNG frames via `exec-out screencap -p` and write real-time paced MP4."""
        start = time.perf_counter()
        writer: cv2.VideoWriter | None = None
        last_frame: np.ndarray | None = None
        last_frame_time: float = start
        frames_captured = 0
        last_err = ""

        try:
            while not self._stop_event.is_set():
                now = time.perf_counter()
                if now - start >= self.max_seconds:
                    break

                raw_bytes, res = self.client.run_binary(
                    ["exec-out", "screencap", "-p"],
                    serial=self.serial,
                    timeout=10.0,
                )
                if not res.ok or not raw_bytes.startswith(PNG_SIGNATURE):
                    last_err = res.stderr or "Invalid PNG frame from screencap."
                    if self._stop_event.wait(0.1):
                        break
                    continue

                frame = cv2.imdecode(np.frombuffer(raw_bytes, np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    continue

                capture_time = time.perf_counter()
                if writer is None:
                    height, width = frame.shape[:2]
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    writer = cv2.VideoWriter(str(out_path), fourcc, _FALLBACK_FPS, (width, height))
                    if not writer.isOpened():
                        return RecordingOutcome(
                            output_path=None,
                            mode="fallback",
                            result=CommandResult(
                                command=["cv2.VideoWriter", str(out_path)],
                                returncode=-1,
                                stderr="Failed to initialize MP4 VideoWriter.",
                            ),
                        )
                elif last_frame is not None:
                    repeat = max(1, round((capture_time - last_frame_time) * _FALLBACK_FPS))
                    for _ in range(repeat):
                        writer.write(last_frame)

                last_frame = frame
                last_frame_time = capture_time
                frames_captured += 1

            if writer is not None and last_frame is not None:
                tail_repeat = max(1, round((time.perf_counter() - last_frame_time) * _FALLBACK_FPS))
                for _ in range(tail_repeat):
                    writer.write(last_frame)
        finally:
            if writer is not None:
                writer.release()

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if frames_captured > 0 and out_path.exists() and out_path.stat().st_size > 0:
            return RecordingOutcome(
                output_path=out_path,
                mode="fallback",
                frames_captured=frames_captured,
                result=CommandResult(
                    command=["exec-out", "screencap", "-p", "->", str(out_path)],
                    returncode=0,
                    stdout=f"Recorded {frames_captured} frames to {out_path.name}",
                    duration_ms=elapsed_ms,
                ),
            )

        return RecordingOutcome(
            output_path=None,
            mode="fallback",
            frames_captured=frames_captured,
            result=CommandResult(
                command=["exec-out", "screencap", "-p"],
                returncode=-1,
                stderr=last_err or "No frames captured.",
                duration_ms=elapsed_ms,
            ),
        )
