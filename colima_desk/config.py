"""Simple JSON-based configuration persisted to a platform-specific dir.

Kept pure-Python so it has no Qt dependency. The GUI reads/writes this and
exposes it through a settings dialog.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from typing import Dict


@dataclass
class ColimaConfig:
    """User-configurable application settings."""

    start_args: list = field(default_factory=list)  # extra args appended to `colima start`
    default_profile: str = "default"
    poll_interval: float = 2.0  # seconds between container-stat refreshes
    auto_start_colima: bool = False  # start Colima automatically on app launch if stopped


def config_dir() -> str:
    """Return the app's per-user config directory (platform-appropriate)."""

    if sys.platform == "win32":
        base = os.path.join(os.path.expandvars("%APPDATA%"), "ColimaDesk")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), ".config", "colima-desk")
    else:
        base = os.path.join(os.path.expanduser("~"), ".config", "colima-desk")
    return base


def config_path() -> str:
    """Absolute path to the config JSON file."""
    return os.path.join(config_dir(), "config.json")


class ColimaConfigStore:
    """Load/save :class:`ColimaConfig`. Safe if the file is missing or corrupt."""

    @classmethod
    def load(cls) -> ColimaConfig:
        path = config_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw: Dict = json.load(fh)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            raw = {}
        return ColimaConfig(
            start_args=list(raw.get("start_args", [])),
            default_profile=str(raw.get("default_profile", ColimaConfig.default_profile)),
            poll_interval=float(raw.get("poll_interval", ColimaConfig.poll_interval)),
            auto_start_colima=bool(raw.get("auto_start_colima", ColimaConfig.auto_start_colima)),
        )

    @classmethod
    def save(cls, cfg: ColimaConfig) -> None:
        d = config_dir()
        os.makedirs(d, exist_ok=True)
        with open(config_path(), "w", encoding="utf-8") as fh:
            json.dump(asdict(cfg), fh, indent=2)

    @classmethod
    def reload(cls) -> ColimaConfig:
        return cls.load()