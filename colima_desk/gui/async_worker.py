"""Worker thread that runs a callable off the GUI thread and delivers its
result (or exception) back via Qt signals.

The worker is meant to be parented by the owning controller (a QObject on the
GUI thread). Because the worker runs on a different thread, signals emitted
here are delivered to connected GUI slots on the main thread via Qt's queued
connection.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    done = Signal(object)
    error = Signal(object)

    def __init__(self, fn: Callable, *args, **kwargs) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            self.done.emit(self._fn(*self._args, **self._kwargs))
        except Exception as exc:  # noqa: BLE001
            self.error.emit(exc)