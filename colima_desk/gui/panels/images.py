"""Images panel."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QInputDialog

from .base_panel import BasePanel
from ...models import Image


class ImagesPanel(BasePanel):
    def __init__(self, app) -> None:
        super().__init__(
            app,
            "Images",
            headers=["Image", "Tag", "ID", "Size", "Created", "Containers"],
            column_widths=[180, 90, 90, 110, 140, 90],
            center_columns=(1, 2, 3, 5),
            empty_title="No images yet",
            empty_hint="Pull an image to get started.",
            empty_stopped_title="Colima is not running",
            empty_stopped_hint="Start Colima to see and manage your images.",
            double_click_hint="Double-click a row to view image details",
        )
        self._add_button(
            "⬇ Pull…", tooltip="Pull an image by name", slot=self._pull,
            action="pull", requires_selection=False,
        )
        self._add_button(
            "🗑 Remove", tooltip="Remove the selected image", slot=self._remove,
            action="remove",
        )

    def _row_key(self, ref: Image) -> str:
        return f"{ref.repository}:{ref.tag}" or ref.id

    def _cell_text(self, ref: Image, col: int) -> str:
        if col == 0:
            return ref.repository or "—"
        if col == 1:
            return ref.tag or "—"
        if col == 2:
            return ref.id
        if col == 3:
            return ref.size or "—"
        if col == 4:
            return ref.created_since or ref.created_at
        if col == 5:
            return str(ref.containers)
        return ""

    def _pull(self, ref: Image) -> None:
        name, ok = QInputDialog.getText(
            self, "Pull Image", "Image name (e.g. alpine:3.20):"
        )
        if ok and name.strip():
            self._app.pull_image(name.strip())

    def _remove(self, ref: Image) -> None:
        message = f'Remove image "{ref.repository}:{ref.tag}"?'
        if ref.containers > 0:
            message += f" This image is in use by {ref.containers} container(s) and will be force-removed."
        if not QMessageBox.question(
            self, "Remove Image",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ):
            return
        image_ref = f"{ref.repository}:{ref.tag}" if ref.tag and ref.tag != "<none>" else ref.repository
        self._app.remove_image(image_ref, force=(ref.containers > 0))

    def _on_cell_double_clicked(self, row: int, _col: int) -> None:
        ref = self._row_to_ref.get(row)
        if ref is None:
            return
        QMessageBox.information(
            self,
            "Image Details",
            f"Image: {ref.repository or '—'}\n"
            f"Tag: {ref.tag or '—'}\n"
            f"ID: {ref.id or '—'}\n"
            f"Size: {ref.size or '—'}\n"
            f"Created: {ref.created_since or ref.created_at or '—'}\n"
            f"Containers: {ref.containers}",
        )
