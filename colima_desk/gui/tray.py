"""System tray icon — the improved cross-platform applet.

On macOS this renders as a menu-bar item; on Linux as a system-tray icon.
It mirrors the engine state and provides quick actions (start/stop, open
the main window, view containers/images/profiles/compose, settings, quit).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .resources import tray_icon, STARTING_COLOR


class SystemTrayIcon(QSystemTrayIcon):
    def __init__(self, app) -> None:
        super().__init__(app.window or None)
        self._app = app
        self._menu = QMenu()
        self._operation: Optional[str] = None

        # Reflect Colima lifecycle operations in the tray icon color.
        app.operation_started.connect(self._on_operation_started)
        app.operation_done.connect(self._on_operation_done)
        # Reflect every state update, including failed refreshes, so the tray
        # icon/tooltip never goes stale after a refresh_state error.
        app.state_changed.connect(self.update_state)

        # Status line (disabled) — mirrors the top-bar badge.
        self._status_action = QAction("Colima: unknown", self._menu)
        self._status_action.setEnabled(False)
        self._menu.addAction(self._status_action)

        self._runtime_action = QAction("", self._menu)
        self._runtime_action.setEnabled(False)
        self._menu.addAction(self._runtime_action)

        self._menu.addSeparator()

        # Start / Stop / Restart
        self._start_action = QAction("▶ Start Colima", self._menu)
        self._start_action.triggered.connect(lambda: self._app.start_profile())
        self._menu.addAction(self._start_action)

        self._stop_action = QAction("⏹ Stop Colima", self._menu)
        self._stop_action.triggered.connect(lambda: self._app.stop_profile())
        self._menu.addAction(self._stop_action)

        self._restart_action = QAction("⟳ Restart Colima", self._menu)
        self._restart_action.triggered.connect(lambda: self._app.restart_profile())
        self._menu.addAction(self._restart_action)

        self._menu.addSeparator()

        self._refresh_action = QAction("⟳ Refresh", self._menu)
        self._refresh_action.triggered.connect(lambda: self._app.refresh_all())
        self._menu.addAction(self._refresh_action)

        self._menu.addSeparator()

        # Window visibility (conditional: only the relevant one is shown).
        self._show_window_action = QAction("Show Window", self._menu)
        self._show_window_action.triggered.connect(self._app.show_window)
        self._menu.addAction(self._show_window_action)

        self._hide_window_action = QAction("Hide Window", self._menu)
        self._hide_window_action.triggered.connect(
            lambda: self._app.window.hide() if self._app.window is not None else None
        )
        self._menu.addAction(self._hide_window_action)

        self._menu.addSeparator()

        # Open main window / panels
        containers_action = QAction("Show Containers…", self._menu)
        containers_action.triggered.connect(lambda: self._open_panel(0))
        self._menu.addAction(containers_action)

        images_action = QAction("Show Images…", self._menu)
        images_action.triggered.connect(lambda: self._open_panel(1))
        self._menu.addAction(images_action)

        compose_action = QAction("Show Compose…", self._menu)
        compose_action.triggered.connect(lambda: self._open_panel(2))
        self._menu.addAction(compose_action)

        profiles_action = QAction("Show Profiles…", self._menu)
        profiles_action.triggered.connect(lambda: self._open_panel(3))
        self._menu.addAction(profiles_action)

        self._menu.addSeparator()

        settings_action = QAction("Settings…", self._menu)
        settings_action.triggered.connect(lambda: self._open_settings())
        self._menu.addAction(settings_action)

        self._menu.addSeparator()

        quit_action = QAction("Quit Colima Desktop", self._menu)
        quit_action.triggered.connect(self._app.quit)
        self._menu.addAction(quit_action)

        self.setContextMenu(self._menu)

        # Single-click does nothing; double-click does not work reliably on
        # macOS status items, so window toggling is done via the menu above.
        self.activated.connect(self._on_activated)

        self.update_state(self._app.state)
        self.update_window_visibility()

    def _open_panel(self, idx: int) -> None:
        self._app.show_window()
        if self._app.window is not None:
            self._app.window._select_panel(idx)

    def _open_settings(self) -> None:
        self._app.show_window()
        if self._app.window is not None:
            self._app.window._open_settings()

    def _on_activated(self, reason) -> None:
        # Intentionally a no-op: single/double clicks do not toggle the
        # window. Visibility is controlled via the menu entries instead.
        return

    def _on_operation_started(self, name: str) -> None:
        if name in ("start", "stop", "restart"):
            self._operation = name
            self.update_state(self._app.state)

    def _on_operation_done(self, name: str, result) -> None:
        if name in ("start", "stop", "restart"):
            self._operation = None
            self.update_state(self._app.state)

    def update_state(self, state) -> None:
        running = bool(getattr(state, "running", False))
        runtime = getattr(state, "runtime", None) or "—"
        engine_missing = self._app.engine is None

        if engine_missing:
            self._status_action.setText("Colima: unavailable")
            self._runtime_action.setText("engine not found")
        elif self._operation in ("start", "stop", "restart"):
            label = {
                "start": "Starting Colima…",
                "stop": "Stopping Colima…",
                "restart": "Restarting Colima…",
            }.get(self._operation, "Working…")
            self._status_action.setText(f"Colima: {label}")
            self._runtime_action.setText(f"runtime: {runtime}")
        else:
            dot = "●" if running else "○"
            self._status_action.setText(
                f"{dot} Colima: {'running' if running else 'stopped'}"
            )
            self._runtime_action.setText(f"runtime: {runtime}")

        self._start_action.setEnabled(not running and not engine_missing)
        self._stop_action.setEnabled(running and not engine_missing)
        self._restart_action.setEnabled(running and not engine_missing)
        self._refresh_action.setEnabled(not engine_missing)
        if self._operation in ("start", "stop", "restart"):
            self.setIcon(tray_icon(running, color=STARTING_COLOR))
        else:
            self.setIcon(tray_icon(running))
        self.setToolTip(
            f"Colima Desktop — {'running' if running else 'stopped'} ({runtime})"
        )
        self.update_window_visibility()

    def update_window_visibility(self) -> None:
        visible = False
        if self._app.window is not None:
            visible = self._app.window.isVisible()
        self._show_window_action.setVisible(not visible)
        self._hide_window_action.setVisible(visible)
