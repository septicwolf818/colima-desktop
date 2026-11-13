"""Shared PATH augmentation for Colima Desk entry points."""

from __future__ import annotations

import os


def augment_path() -> None:
    """Ensure Homebrew / common tool paths are available on ``PATH``.

    Packaged apps (PyInstaller) inherit a minimal PATH that excludes
    ``/opt/homebrew/bin``, so colima's subprocesses (limactl, docker, ...)
    would fail to launch.
    """
    _extra = [
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        "/usr/local/sbin",
        os.path.join(os.path.expanduser("~"), ".local", "bin"),
    ]
    _current = os.environ.get("PATH", "")
    for _p in _extra:
        if _p not in _current.split(os.pathsep):
            _current = _p + os.pathsep + _current
    os.environ["PATH"] = _current
