"""Background worker utilities for running ADB tasks off the Qt UI thread."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
    """Signals emitted by an AsyncTask."""

    finished = Signal(object)
    failed = Signal(str)


class AsyncTask(QRunnable):
    """Run any callable in QThreadPool and emit its result or error message."""

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        # Python owns lifetime via MainWindow._pending_tasks until signal delivery completes.
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(str(exc))
