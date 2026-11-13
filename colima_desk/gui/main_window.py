"""Main window — the Docker-Desktop-style colima management UI."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFont, QFontDatabase, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import resources
from .panels import ContainersPanel, ImagesPanel, ProfilesPanel, ComposePanel
from .status_bar import TopStatusBar
from .fonts import _mono_font


class MainWindow(QMainWindow):
    """The main application window."""

    def __init__(self, app) -> None:
        super().__init__()
        self._app = app

        self.setWindowTitle("Colima Desktop")
        self.setWindowIcon(resources.app_logo())
        self.setMinimumSize(960, 600)
        # Restore the previous window geometry (falls back to a sensible size).
        settings = QSettings()
        geometry = settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1200, 760)
        # Closing the window hides it (app keeps running in the tray).
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        self._panels_order = ["containers", "images", "compose", "profiles"]
        self._panels = {}
        self._nav_buttons = []

        # ── central widget ──────────────────────────────────────────────
        central = QWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # top bar
        self.top_bar = TopStatusBar(
            app,
            on_start=lambda: self._app.start_profile(self._app.config.default_profile),
            on_stop=lambda: self._app.stop_profile(self._app.config.default_profile),
            on_restart=lambda: self._app.restart_profile(self._app.config.default_profile),
            on_refresh=lambda: self._app.refresh_all(),
        )
        root_layout.addWidget(self.top_bar)

        # body: sidebar + content
        body_layout = QHBoxLayout()
        body_layout.setSpacing(0)
        body_layout.setContentsMargins(0, 0, 0, 0)

        sidebar = self._build_sidebar()
        body_layout.addWidget(sidebar, 0)

        self._stack = QStackedWidget()
        self._panels["containers"] = ContainersPanel(app)
        self._panels["images"] = ImagesPanel(app)
        self._panels["compose"] = ComposePanel(app)
        self._panels["profiles"] = ProfilesPanel(app)
        for key in self._panels_order:
            self._stack.addWidget(self._panels[key])
        body_layout.addWidget(self._stack, 1)

        root_layout.addLayout(body_layout, 1)

        # bottom terminal-like log view (header + dark console)
        root_layout.addWidget(self._build_console_bar())
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(_mono_font())
        self._log.setStyleSheet(
            "background:#1e1e1e; color:#d4d4d4; border:none; "
            "border-top:1px solid #333; padding:4px 8px;"
        )
        self._log.setMinimumHeight(110)
        self._log.setMaximumHeight(220)
        self._log.setPlaceholderText("Colima Desktop log output…")
        self._log.document().setMaximumBlockCount(5000)
        self._log.setContextMenuPolicy(Qt.CustomContextMenu)
        self._log.customContextMenuRequested.connect(self._show_log_context_menu)
        root_layout.addWidget(self._log)

        self.setCentralWidget(central)

        self._build_menu_bar()

        # connect app signals
        self._app.state_changed.connect(self._on_state_changed)
        self._app.app_log.connect(self.append_log)
        self._app.operation_started.connect(self._on_operation_started)
        self._app.operation_output.connect(self._on_operation_output)
        self._app.operation_done.connect(self._on_operation_done)
        self._app.containers_loaded.connect(self._on_containers_loaded)
        self._app.images_loaded.connect(self._on_images_loaded)
        self._app.compose_projects_loaded.connect(self._on_compose_loaded)
        self._app.profiles_loaded.connect(self._on_profiles_loaded)

        # default panel (restored from settings when available)
        try:
            last_panel = int(settings.value("lastPanel", 0))
        except (TypeError, ValueError):
            last_panel = 0
        if not 0 <= last_panel < len(self._panels_order):
            last_panel = 0
        self._stack.setCurrentIndex(last_panel)
        self._highlight_nav(last_panel)

        self._install_shortcuts()

    # ── console ──────────────────────────────────────────────────────────

    def _build_console_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet("background:#f9fafb; border-bottom:1px solid #e5e7eb;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(6)
        label = QLabel("Console")
        label.setStyleSheet(
            "color:#6b7280; font-size:11px; font-weight:600; background:transparent;"
        )
        layout.addWidget(label)
        layout.addStretch(1)
        clear_btn = QPushButton("Clear")
        clear_btn.setProperty("flatButton", True)
        clear_btn.setToolTip("Clear the console output")
        clear_btn.clicked.connect(self.clear_log)
        layout.addWidget(clear_btn)
        return bar

    def _show_log_context_menu(self, pos) -> None:
        menu = QMenu(self)
        copy_action = menu.addAction("Copy")
        select_all_action = menu.addAction("Select All")
        menu.addSeparator()
        clear_action = menu.addAction("Clear")
        menu.addSeparator()
        scroll_action = menu.addAction("Scroll to Bottom")
        chosen = menu.exec(self._log.viewport().mapToGlobal(pos))
        if chosen == copy_action:
            self._log.copy()
        elif chosen == select_all_action:
            self._log.selectAll()
        elif chosen == clear_action:
            self.clear_log()
        elif chosen == scroll_action:
            self._scroll_log_to_bottom()

    # ── menu bar ─────────────────────────────────────────────────────────

    def _build_menu_bar(self) -> None:
        bar = self.menuBar()
        # File
        file_menu = bar.addMenu("&File")
        settings_action = file_menu.addAction("&Settings…")
        settings_action.setShortcut(QKeySequence.Preferences)
        settings_action.triggered.connect(self._open_settings)
        file_menu.addSeparator()
        quit_action = file_menu.addAction("&Quit Colima Desktop")
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self._app.quit)
        # View
        view_menu = bar.addMenu("&View")
        refresh_action = view_menu.addAction("&Refresh")
        refresh_action.setShortcut(QKeySequence.Refresh)
        refresh_action.triggered.connect(lambda: self._app.refresh_all())
        view_menu.addSeparator()
        for idx, name in enumerate(self._panels_order):
            a = view_menu.addAction(f"Show {name.title()}")
            a.triggered.connect(lambda _=None, i=idx: self._select_panel(i))
        # Help
        help_menu = bar.addMenu("&Help")
        about_action = help_menu.addAction("&About Colima Desktop")
        about_action.triggered.connect(self._show_about)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About Colima Desktop",
            "<b>Colima Desktop</b> 0.1.0<br>"
            "A Docker-Desktop-style manager for Colima.<br><br>"
            "Manage Colima profiles, containers, images, and compose stacks.<br>"
            "Cross-platform: macOS and Linux.",
        )

    # ── sidebar ──────────────────────────────────────────────────────────

    def _build_sidebar(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(190)
        w.setStyleSheet(
            "background:#f5f6f8; border-right:1px solid #e1e4e8; "
            "color:#1f2937;"
        )
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 16, 12, 12)
        v.setSpacing(6)

        brand = QLabel("Colima Desktop")
        brand.setFont(self._brand_font())
        brand.setAlignment(Qt.AlignHCenter)
        brand.setStyleSheet("color:#111827; background:transparent;")
        v.addWidget(brand)

        subtitle = QLabel("Manage with Colima")
        subtitle.setStyleSheet("color:#6b7280; font-size:11px; background:transparent;")
        subtitle.setAlignment(Qt.AlignHCenter)
        v.addWidget(subtitle)
        v.addSpacing(12)

        items = [
            ("containers", "📦  Containers", "Show containers"),
            ("images", "🖼  Images", "Show images"),
            ("compose", "🧩  Compose", "Show compose stacks"),
            ("profiles", "🏗  Profiles", "Show profiles"),
        ]
        for idx, (key, label, tip) in enumerate(items):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setProperty("nav", True)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _=None, k=idx: self._select_panel(k))
            self._nav_buttons.append(btn)
            v.addWidget(btn)

        v.addStretch(1)

        # separator above the utility buttons
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet("background:#e5e7eb; border:none;")
        v.addWidget(line)
        v.addSpacing(8)

        settings_btn = QPushButton("⚙  Settings")
        settings_btn.setProperty("nav", True)
        settings_btn.setToolTip("Open settings  (Ctrl/Cmd+,)")
        settings_btn.clicked.connect(self._open_settings)
        v.addWidget(settings_btn)

        quit_btn = QPushButton("⏻  Quit")
        quit_btn.setProperty("danger", True)
        quit_btn.setToolTip("Quit Colima Desktop  (Ctrl/Cmd+Q)")
        quit_btn.clicked.connect(self._app.quit)
        v.addWidget(quit_btn)
        return w

    def _brand_font(self) -> QFont:
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        return f

    # ── shortcuts ────────────────────────────────────────────────────────

    def _install_shortcuts(self) -> None:
        # F5 → refresh_all (no menu binding for this key).
        QShortcut(QKeySequence("F5"), self, self._app.refresh_all)

    # ── panel switching ─────────────────────────────────────────────────

    def _select_panel(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)
        self._highlight_nav(idx)

    def _highlight_nav(self, idx: int) -> None:
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == idx)
            if i == idx:
                btn.setStyleSheet(
                    "padding:10px 14px; border:none; border-radius:8px; "
                    "font-weight:600; text-align:left; font-size:13px; "
                    "color:#ffffff; background:#228F48;"
                )
            else:
                btn.setStyleSheet(
                    "padding:10px 14px; border:none; border-radius:8px; "
                    "font-weight:500; text-align:left; font-size:13px; "
                    "color:#374151; background:transparent;"
                )

    # ── app-signal handlers ─────────────────────────────────────────────

    def _on_state_changed(self, state) -> None:
        self.top_bar.set_state(state.running, state.runtime, state.error)
        if not state.running:
            self.top_bar.usage_label.hide()
        self._panels["containers"].enable_actions(state.running)
        self._panels["images"].enable_actions(state.running)
        self._panels["compose"].enable_actions(state.running)
        # Reflect the Colima state in the window title.
        if getattr(state, "running", False):
            self.setWindowTitle("Colima Desktop — running")
        else:
            self.setWindowTitle("Colima Desktop — stopped")

    def _on_operation_started(self, name: str) -> None:
        # Only Colima lifecycle operations drive the top-bar indicator.
        if name in ("start", "stop", "restart"):
            self.top_bar.set_operation(name)
        self.setWindowTitle(f"Colima Desktop — {name}…")
        self.append_log(f"\x1b[36m→ requesting: {name}\x1b[0m")

    def _on_operation_output(self, name: str, line: str) -> None:
        # Stream live output to the terminal.
        self.append_log(line.rstrip("\n"))

    def _on_operation_done(self, name: str, result) -> None:
        # Only Colima lifecycle operations drive the top-bar indicator.
        if name in ("start", "stop", "restart"):
            self.top_bar.clear_operation()
        # Only append the result line — the command output was already streamed
        # live via operation_output, so re-appending it would duplicate.
        color = "#4ade80" if result.success else "#f87171"
        icon = "✓" if result.success else "✗"
        # Don't duplicate the streamed command output in the status line —
        # it's already shown above. Use a concise, predefined message.
        if result.success:
            status = "done"
        else:
            text = result.stderr.strip() or result.stdout.strip()
            status = text.splitlines()[0][:120] if text else "failed"
        self.append_log(
            f'\x1b[{"32" if result.success else "31"}m{icon} {name} — {status}\x1b[0m'
        )
        # The controller already refreshed everything in _after_op(); avoid a
        # second full refresh here.

    def append_log(self, text: str) -> None:
        from .dialogs import ansi_to_html
        sb = self._log.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        self._log.append(
            f'<pre style="margin:0; white-space:pre-wrap;">{ansi_to_html(text)}</pre>'
        )
        # Only follow the tail when the user is already at the bottom; never
        # yank someone back down while they are reading older output.
        if at_bottom:
            sb.setValue(sb.maximum())

    def clear_log(self) -> None:
        self._log.clear()

    def _scroll_log_to_bottom(self) -> None:
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_containers_loaded(self, refs, stats) -> None:
        self._panels["containers"].populate(
            refs, disabled=not self._app.colima_running, stats=stats
        )

    def _on_images_loaded(self, refs) -> None:
        self._panels["images"].populate(
            refs, disabled=not self._app.colima_running
        )

    def _on_compose_loaded(self, refs) -> None:
        self._panels["compose"].populate(
            refs, disabled=not self._app.colima_running
        )

    def _on_profiles_loaded(self, refs) -> None:
        self._panels["profiles"].populate(refs, disabled=False)

    # ── window state ────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        settings = QSettings()
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("lastPanel", self._stack.currentIndex())
        settings.sync()
        super().closeEvent(event)

    # ── helpers ──────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._app.tray is not None:
            self._app.tray.update_window_visibility()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if self._app.tray is not None:
            self._app.tray.update_window_visibility()

    def _open_settings(self) -> None:
        from .dialogs import SettingsDialog
        dlg = SettingsDialog(self._app)
        if dlg.exec():
            self._app.refresh_all()
