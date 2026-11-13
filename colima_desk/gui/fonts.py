"""Shared font helpers for Colima Desktop GUI."""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase

_MONO_FAMILY = "Menlo, Monaco, Courier New, monospace"


def _mono_font() -> QFont:
    """Cross-platform monospaced font for console / log views."""
    f = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    f.setPointSize(11)
    return f
