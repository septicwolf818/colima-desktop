"""Engine package: pure-Python colima / container / image operations.

No Qt dependency. Import :class:`ColimaEngine` from here to get the whole
lifecycle + container + image surface.
"""

from __future__ import annotations

from .colima_engine import ColimaEngine, EngineError

__all__ = ["ColimaEngine", "EngineError"]