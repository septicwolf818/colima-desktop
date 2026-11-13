"""Resource helpers: build QIcon objects programmatically (no image files).

Keeping icons code-generated means the app ships with zero binary assets and
looks the same on macOS and Linux.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QIcon, QPixmap, QColor, QPen


# ── status colors ───────────────────────────────────────────────────────────

RUNNING_COLOR = QColor(32, 143, 72)     # green
STOPPED_COLOR = QColor(153, 153, 153)   # gray
STARTING_COLOR = QColor(240, 173, 20)   # amber
ERROR_COLOR = QColor(213, 53, 38)       # red


def _rounded_square(size: int, color: QColor, inner: bool = True, dot: bool = True) -> QIcon:
    """Draw a rounded square badge with an optional inner dot."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(Qt.NoPen))
    p.setBrush(color)
    p.drawRoundedRect(0, 0, size, size, size // 3, size // 3)
    if inner and dot:
        p.setBrush(QColor(255, 255, 255, 220))
        inner = size // 5
        p.drawEllipse(QPointF(size / 2 - inner / 2, size / 2 - inner / 2), inner / 2, inner / 2)
    p.end()
    icon = QIcon(pix)
    return icon


def status_icon(running: bool) -> QIcon:
    """Tray + top-bar status badge (running vs stopped)."""
    return _rounded_square(64, RUNNING_COLOR if running else STOPPED_COLOR)


def tray_icon(running: bool, size: int = 44, color: Optional[QColor] = None) -> QIcon:
    """A polished tray icon: a rounded-square badge with a white 'C' arc.

    Green when Colima is running, gray when stopped, amber while an operation
    is in progress. Designed to read well at macOS menu-bar size (18-22pt)
    and on Linux tray.
    """
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    if color is None:
        color = RUNNING_COLOR if running else STOPPED_COLOR

    # Gradient background.
    from PySide6.QtGui import QLinearGradient
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, color)
    grad.setColorAt(1.0, color.darker(125))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    radius = size // 4
    p.drawRoundedRect(0, 0, size, size, radius, radius)

    # Subtle top highlight.
    hl = QLinearGradient(0, 0, 0, size // 2)
    hl.setColorAt(0.0, QColor(255, 255, 255, 50))
    hl.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(hl)
    p.drawRoundedRect(0, 0, size, size // 2, radius, radius)

    # White "C" arc.
    stroke = max(2, size // 12)
    p.setPen(QPen(QColor(255, 255, 255), stroke, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    margin = size // 4
    p.drawArc(
        margin, margin,
        size - 2 * margin, size - 2 * margin,
        40 * 16, 280 * 16,
    )
    if running:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 230))
        dot = size // 7
        p.drawEllipse(size - margin - dot, size // 2 - dot // 2, dot, dot)
    p.end()
    return QIcon(pix)


def icon_status_color(color: QColor, size: int = 64) -> QIcon:
    return _rounded_square(size, color)


def icon_for_label(label: str) -> QIcon:
    """Draw a small monochrome glyph for sidebar rows.

    Returns a simple 16x16 icon: a rounded square in a neutral gray. We
    rely on the text label to convey meaning, so this is intentionally
    minimal and cross-platform.
    """
    pix = QPixmap(32, 32)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(120, 120, 120)))
    p.setPen(QPen(QColor(120, 120, 120), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.transparent)
    cx, cy = 16.0, 16.0
    r = 10.0
    p.drawEllipse(cx, cy, r, r)
    p.end()
    return QIcon(pix)


def pull_request_icon() -> QIcon:
    return _rounded_square(64, QColor(0, 122, 255))


def app_logo(size: int = 96) -> QIcon:
    """App logo: a gradient rounded-square with a bold white 'C' arc.

    Inspired by the Colima branding (green/teal) but refined for an app icon.
    """
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    # Gradient background (green -> teal).
    from PySide6.QtGui import QLinearGradient
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#228F48"))
    grad.setColorAt(1.0, QColor("#0d9488"))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    radius = size // 4
    p.drawRoundedRect(0, 0, size, size, radius, radius)

    # Subtle top highlight.
    hl = QLinearGradient(0, 0, 0, size // 2)
    hl.setColorAt(0.0, QColor(255, 255, 255, 60))
    hl.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(hl)
    p.drawRoundedRect(0, 0, size, size // 2, radius, radius)

    # Bold white "C" arc.
    stroke = max(3, size // 12)
    p.setPen(QPen(QColor(255, 255, 255), stroke, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    margin = size // 5
    p.drawArc(
        margin, margin,
        size - 2 * margin, size - 2 * margin,
        40 * 16, 280 * 16,
    )
    # Small accent dot (container) inside the C.
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 200))
    dot = size // 9
    cx = size // 2 + size // 8
    cy = size // 2
    p.drawEllipse(cx - dot // 2, cy - dot // 2, dot, dot)
    p.end()
    return QIcon(pix)