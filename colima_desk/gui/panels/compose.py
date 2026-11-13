"""Compose stacks panel — group containers by compose project and manage
the whole stack (start/stop/delete) like Docker Desktop."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from .base_panel import BasePanel
from ...models import ComposeProject


class ComposePanel(BasePanel):
    def __init__(self, app) -> None:
        super().__init__(
            app,
            "Compose Stacks",
            headers=["Project", "Status", "Containers", "Config File"],
            column_widths=[160, 110, 100, 320],
            center_columns=(1, 2),
            empty_title="No compose stacks yet",
            empty_hint="Run docker compose up in a project to see it here.",
            empty_stopped_title="Colima is not running",
            empty_stopped_hint="Start Colima to see and manage your compose stacks.",
            double_click_hint="Double-click a row to view stack logs",
        )
        self._add_button(
            "▶ Start", tooltip="Start the whole stack (up -d)", slot=self._start,
            action="start",
        )
        self._add_button(
            "⏹ Stop", tooltip="Stop the whole stack", slot=self._stop,
            action="stop",
        )
        self._add_button(
            "🗑 Down", tooltip="Take the stack down (remove containers)", slot=self._down,
            action="down",
        )
        self._add_button(
            "📄 Logs…", tooltip="View logs for this stack", slot=self._logs,
            action="logs",
        )

    def _is_action_enabled(self, action: str, ref: ComposeProject) -> bool:
        if action in ("start", "down"):
            return bool(ref.config_files)
        if action in ("stop", "logs"):
            return True
        return True

    def _logs(self, ref: ComposeProject) -> None:
        self._app.show_compose_logs(ref)

    def _cell_text(self, ref: ComposeProject, col: int) -> str:
        if col == 0:
            return ref.name
        if col == 1:
            return f"● {ref.status}" if ref.running else ref.status
        if col == 2:
            return str(ref.container_count)
        if col == 3:
            return ref.config_files or ref.working_dir or "—"
        return ""

    def _start(self, ref: ComposeProject) -> None:
        if not ref.config_files:
            return
        self._app.compose_up(ref.config_files)

    def _stop(self, ref: ComposeProject) -> None:
        if not ref.config_files:
            return
        self._app.compose_stop(ref.config_files)

    def _down(self, ref: ComposeProject) -> None:
        if not ref.config_files:
            return
        if not QMessageBox.question(
            self, "Take Down Stack",
            f'Take down compose stack "{ref.name}"? This removes its containers.',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ):
            return
        self._app.compose_down(ref.config_files)

    def _on_cell_double_clicked(self, row: int, _col: int) -> None:
        ref = self._row_to_ref.get(row)
        if ref is not None:
            self._app.show_compose_logs(ref)
