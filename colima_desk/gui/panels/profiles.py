"""Profiles panel (colima's multi-instance units — the user's "projects")."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from .base_panel import BasePanel
from ...models import Profile


class ProfilesPanel(BasePanel):
    def __init__(self, app) -> None:
        super().__init__(
            app,
            "Profiles (Projects)",
            headers=["Profile", "Status", "Runtime", "CPUs", "Memory", "Disk"],
            column_widths=[140, 110, 140, 80, 100, 100],
            center_columns=(1, 2, 3, 4, 5),
            empty_title="No profiles yet",
            empty_hint="Create a profile with colima start --profile <name>.",
            empty_stopped_title="No profiles yet",
            empty_stopped_hint="Create a profile with `colima start --profile <name>`.",
            double_click_hint="Double-click a row to edit the profile",
        )
        self._add_button(
            "▶ Start", tooltip="Start the selected profile", slot=self._start,
            action="start",
        )
        self._add_button(
            "⏹ Stop", tooltip="Stop the selected profile", slot=self._stop,
            action="stop",
        )
        self._add_button(
            "⟳ Restart", tooltip="Restart the selected profile", slot=self._restart,
            action="restart",
        )
        self._add_button(
            "🗑 Delete", tooltip="Delete the selected profile", slot=self._delete,
            action="delete",
        )

    def _is_action_enabled(self, action: str, ref: Profile) -> bool:
        if action == "start":
            return not ref.running
        if action in ("stop", "restart"):
            return ref.running
        return True

    def _cell_text(self, ref: Profile, col: int) -> str:
        if col == 0:
            return ref.name
        if col == 1:
            return f"● {ref.status}" if ref.running else ref.status
        if col == 2:
            return ref.runtime or "—"
        if col == 3:
            return ref.cpus or "—"
        if col == 4:
            return ref.memory or "—"
        if col == 5:
            return ref.disk or "—"
        return ""

    def _start(self, ref: Profile) -> None:
        if ref.running:
            return
        self._app.start_profile(ref.name)

    def _stop(self, ref: Profile) -> None:
        if not ref.running:
            return
        self._app.stop_profile(ref.name)

    def _restart(self, ref: Profile) -> None:
        if ref.running:
            self._app.restart_profile(ref.name)

    def _delete(self, ref: Profile) -> None:
        if not QMessageBox.question(
            self, "Delete Profile",
            f"Delete profile \"{ref.name}\"? This tears down its VM.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ):
            return
        self._app.delete_profile(ref.name)

    def _on_cell_double_clicked(self, row: int, _col: int) -> None:
        ref = self._row_to_ref.get(row)
        if ref is not None:
            from ..dialogs import ProfileEditorDialog
            dlg = ProfileEditorDialog(self._app, ref)
            if dlg.exec():
                self._app.refresh_profiles()
