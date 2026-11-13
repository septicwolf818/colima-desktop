"""Containers panel."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from .base_panel import BasePanel
from ...models import Container


class ContainersPanel(BasePanel):
    def __init__(self, app) -> None:
        super().__init__(
            app,
            "Containers",
            headers=["Container", "Project", "Image", "Status", "CPU", "Memory", "Ports", "Size"],
            column_widths=[150, 120, 130, 120, 70, 120, 160, 100],
            center_columns=(3, 4, 5),
            empty_title="No containers yet",
            empty_hint="Run a container or pull an image to get started.",
            empty_stopped_title="Colima is not running",
            empty_stopped_hint="Start Colima to see and manage your containers.",
            double_click_hint="Double-click a row to view container logs",
        )
        self._add_button(
            "▶ Start", tooltip="Start the selected container", slot=self._start,
            action="start",
        )
        self._add_button(
            "⏹ Stop", tooltip="Stop the selected container", slot=self._stop,
            action="stop",
        )
        self._add_button(
            "🗑 Remove", tooltip="Remove the selected container", slot=self._remove,
            action="remove",
        )
        self._add_button(
            "📄 Logs…", tooltip="Show recent logs", slot=self._logs,
            action="logs",
        )

    def _is_action_enabled(self, action: str, ref: Container) -> bool:
        if action == "start":
            return not ref.is_running
        if action == "stop":
            return ref.is_running
        return True

    def _stat_for(self, ref: Container):
        return self._stats.get(ref.short_id, self._stats.get(ref.id))

    def _cell_text(self, ref: Container, col: int) -> str:
        if col == 0:
            return ref.name or ref.id
        if col == 1:
            return ref.project or "—"
        if col == 2:
            return ref.image or "—"
        if col == 3:
            return f"● {ref.status}" if ref.is_running else ref.status
        if col == 4:
            s = self._stat_for(ref)
            return (s.cpu if s else "—")
        if col == 5:
            s = self._stat_for(ref)
            return (s.memory if s else "—")
        if col == 6:
            return ref.ports or "—"
        if col == 7:
            return ref.size or "—"
        return ""

    def _start(self, ref: Container) -> None:
        if ref.is_running:
            return
        self._app.start_container(ref.name or ref.id)

    def _stop(self, ref: Container) -> None:
        if not ref.is_running:
            return
        self._app.stop_container(ref.name or ref.id)

    def _remove(self, ref: Container) -> None:
        message = f'Remove container "{ref.name or ref.id}"?'
        if ref.is_running:
            message += " It is currently running; this will be force-removed."
        if not QMessageBox.question(
            self, "Remove Container",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ):
            return
        self._app.remove_container(ref.name or ref.id, force=ref.is_running)

    def _logs(self, ref: Container) -> None:
        self._app.show_container_logs(ref.name or ref.id)

    def _on_cell_double_clicked(self, row: int, _col: int) -> None:
        ref = self._row_to_ref.get(row)
        if ref is not None:
            self._app.show_container_logs(ref.name or ref.id)
