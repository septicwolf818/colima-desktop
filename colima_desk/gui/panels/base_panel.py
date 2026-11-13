"""Shared base for the main-window content panels (containers / images /
profiles / compose).

Each panel owns a QTableWidget, an empty-state placeholder and a row of
action buttons, and exposes `populate(...)` / `selected_ref()` / `refresh()`
for the controller.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedLayout,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...models import OperationResult


class BasePanel(QWidget):
    """Base panel with a table, an empty-state page and an action button row."""

    def __init__(
        self,
        app,
        title: str,
        headers: Sequence[str],
        *,
        column_widths: Optional[Sequence[int]] = None,
        center_columns: Sequence[int] = (),
        empty_title: str = "Nothing here yet",
        empty_hint: str = "",
        empty_stopped_title: str = "Colima is not running",
        empty_stopped_hint: str = "Start Colima to see this content.",
        double_click_hint: str = "Double-click a row to open details",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._app = app
        self._refs: List[Any] = []
        self._row_to_ref: Dict[int, Any] = {}
        self._actions_enabled: bool = True
        self._center_columns = set(center_columns)
        self._empty_title = empty_title
        self._empty_hint = empty_hint
        self._empty_stopped_title = empty_stopped_title
        self._empty_stopped_hint = empty_stopped_hint
        self._double_click_hint = double_click_hint
        # (button, requires_selection, action)
        self._button_specs: List[Tuple[QPushButton, bool, str]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(8)

        header = QLabel(title)
        header.setFont(self._big_font())
        header.setStyleSheet("background:transparent;")
        layout.addWidget(header)

        # ── table + empty state, swapped by a stacked layout ──────────────
        self._table_stack = QStackedLayout()
        self.table = QTableWidget()
        self.table.setColumnCount(len(headers))
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(True)
        self.table.setCursor(Qt.PointingHandCursor)
        self.table.setToolTip(self._double_click_hint)
        for i, h in enumerate(headers):
            self.table.setHorizontalHeaderItem(i, QTableWidgetItem(h))
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.Interactive)
        header_view.setStretchLastSection(True)
        header_view.setMinimumSectionSize(48)
        if column_widths:
            for i, w in enumerate(column_widths):
                if i < self.table.columnCount():
                    self.table.setColumnWidth(i, w)
        self.table.setSortingEnabled(False)
        self.table.itemSelectionChanged.connect(self._update_button_states)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self._table_stack.addWidget(self.table)

        # Empty-state page: a centered icon, title and hint.
        empty_page = QWidget()
        empty_page.setStyleSheet("background:transparent;")
        empty_layout = QVBoxLayout(empty_page)
        empty_layout.addStretch(1)
        self._empty_icon = QLabel("📭")
        self._empty_icon.setAlignment(Qt.AlignCenter)
        self._empty_icon.setStyleSheet("font-size:34px; background:transparent;")
        empty_layout.addWidget(self._empty_icon)
        empty_layout.addSpacing(6)
        self._empty_title_label = QLabel(self._empty_title)
        self._empty_title_label.setAlignment(Qt.AlignCenter)
        self._empty_title_label.setWordWrap(True)
        self._empty_title_label.setProperty("emptyTitle", True)
        empty_layout.addWidget(self._empty_title_label)
        self._empty_hint_label = QLabel(self._empty_hint)
        self._empty_hint_label.setAlignment(Qt.AlignCenter)
        self._empty_hint_label.setWordWrap(True)
        self._empty_hint_label.setProperty("emptyHint", True)
        empty_layout.addWidget(self._empty_hint_label)
        empty_layout.addStretch(1)
        self._table_stack.addWidget(empty_page)
        layout.addLayout(self._table_stack, 1)

        # action bar
        self.toolbar = QWidget()
        bar_layout = QHBoxLayout(self.toolbar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(6)
        self.toolbar._buttons: List[QPushButton] = []
        self._toolbar_layout = bar_layout
        self._build_toolbar(self.toolbar)
        layout.addWidget(self.toolbar)

        # Enter on a selected row triggers the same action as double-click.
        self._enter_shortcut = QShortcut(QKeySequence(Qt.Key_Return), self.table)
        self._enter_shortcut.setContext(Qt.WidgetShortcut)
        self._enter_shortcut.activated.connect(self._on_enter_pressed)

        self._update_button_states()
        self._update_empty_state()

    # ── toolbar / actions ───────────────────────────────────────────────────

    def _big_font(self) -> QFont:
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        return f

    def _build_toolbar(self, _bar: QWidget) -> None:
        # Subclasses add their buttons after super().__init__() returns.
        pass

    def _add_button(
        self,
        text: str,
        *,
        tooltip: Optional[str] = None,
        slot: Optional[Callable[[Any], None]] = None,
        icon: Optional[QIcon] = None,
        action: str = "",
        requires_selection: bool = True,
    ) -> QPushButton:
        btn = QPushButton(text)
        if tooltip is not None:
            btn.setToolTip(tooltip)
        if icon is not None:
            btn.setIcon(icon)
        btn.setEnabled(False)
        self.toolbar._buttons.append(btn)
        self._button_specs.append((btn, requires_selection, action))
        if slot is not None:
            btn.clicked.connect(
                lambda _=btn, r=requires_selection: self._run_action(slot, r)
            )
        self._toolbar_layout.addWidget(btn)
        return btn

    def _run_action(self, slot: Callable, requires_selection: bool) -> None:
        ref = self.selected_ref()
        if ref is None and requires_selection:
            QMessageBox.warning(self, "No selection", "Select an item first.")
            return
        slot(ref)

    def _is_action_enabled(self, action: str, ref: Any) -> bool:
        """Per-panel predicate for selection-dependent buttons."""
        return True

    def _update_button_states(self) -> None:
        ref = self.selected_ref()
        has_selection = ref is not None
        for btn, requires_selection, action in self._button_specs:
            enabled = self._actions_enabled
            if requires_selection:
                enabled = (
                    enabled
                    and has_selection
                    and self._is_action_enabled(action, ref)
                )
            btn.setEnabled(enabled)

    def enable_actions(self, enabled: bool) -> None:
        """Enable/disable the panel's action buttons (driven by colima state)."""
        self._actions_enabled = enabled
        self._update_button_states()
        self._update_empty_state()

    # ── public API ─────────────────────────────────────────────────────────

    def populate(
        self, refs: Sequence[Any], *, disabled: bool = False, stats=None
    ) -> None:
        """Rebuild the table from a list of model objects, preserving selection."""
        # Remember currently selected keys so we can re-select after rebuild.
        selected_keys = {self._row_key(r) for r in self.selected_refs()}

        self._refs = list(refs)
        self._stats = stats or {}
        self._row_to_ref.clear()
        self.table.setRowCount(0)
        for i, ref in enumerate(self._refs):
            self._add_row(i, ref)

        # Re-select rows whose key matches a previously selected one.
        for row, ref in self._row_to_ref.items():
            if self._row_key(ref) in selected_keys:
                self.table.setCurrentCell(row, 0)
                self.table.selectRow(row)

        self.enable_actions(not disabled)

    def _row_key(self, ref: Any) -> str:
        """Unique key used to preserve selection across refreshes."""
        return str(getattr(ref, "name", None) or getattr(ref, "id", None) or ref)

    def _add_row(self, index: int, ref: Any) -> None:
        self.table.insertRow(index)
        for col in range(self.table.columnCount()):
            item = QTableWidgetItem(self._cell_text(ref, col))
            if col in self._center_columns:
                item.setTextAlignment(Qt.AlignCenter)
            else:
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(index, col, item)
        self._row_to_ref[index] = ref

    def _cell_text(self, ref: Any, col: int) -> str:
        raise NotImplementedError

    def selected_ref(self) -> Optional[Any]:
        row = self.table.currentRow()
        return self._row_to_ref.get(row) if row >= 0 else None

    def selected_refs(self) -> List[Any]:
        out: List[Any] = []
        for idx in self.table.selectionModel().selectedRows():
            ref = self._row_to_ref.get(idx.row())
            if ref is not None:
                out.append(ref)
        return out

    def refresh(self) -> None:
        """Optional: let the app drive refreshes. Default no-op."""
        pass

    # ── empty state / interaction ───────────────────────────────────────────

    def _update_empty_state(self) -> None:
        if self.table.rowCount() > 0:
            self._table_stack.setCurrentIndex(0)
            return
        if not self._actions_enabled:
            title, hint = self._empty_stopped_title, self._empty_stopped_hint
            icon = "⏸"
        else:
            title, hint = self._empty_title, self._empty_hint
            icon = "📭"
        self._empty_icon.setText(icon)
        self._empty_title_label.setText(title)
        self._empty_hint_label.setText(hint)
        self._empty_hint_label.setVisible(bool(hint))
        self._table_stack.setCurrentIndex(1)

    def _on_enter_pressed(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self._on_cell_double_clicked(row, 0)

    def _on_current_changed(self, _cur, _prev) -> None:
        pass

    # ── helpers ───────────────────────────────────────────────────────────

    def _notify(self, result: OperationResult, title: str = "Result") -> None:
        if not result.success:
            QMessageBox.information(
                self,
                title,
                f"{result.message}\n\nReturn code: {result.returncode}",
            )

    def _show_error(self, err: Any, title: str = "Error") -> None:
        QMessageBox.critical(self, title, str(err))
