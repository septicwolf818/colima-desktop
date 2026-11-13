"""Top status bar: colima state badge + runtime + Start/Stop/Restart/Refresh
+ an aggregate CPU/RAM readout and an operation progress indicator."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QWidget,
)


class TopStatusBar(QWidget):
    def __init__(
        self,
        app,
        *,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_restart: Callable[[], None],
        on_refresh: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._app = app
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_restart = on_restart
        self._on_refresh = on_refresh

        self.setStyleSheet("background:#fafafa; border-bottom:1px solid #e5e7eb;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # State badge (dot + text) + runtime.
        self.state_dot = QLabel("●")
        self.state_dot.setFixedSize(20, 20)
        self.state_dot.setAlignment(Qt.AlignCenter)
        self.state_label = QLabel("Colima")
        self.state_label.setStyleSheet("font-size:13px; font-weight:600; color:#1f2937;")
        self.runtime_label = QLabel("")
        self.runtime_label.setStyleSheet("font-size:11px; color:#888;")

        # Aggregate usage badge (hidden until stats arrive).
        self.usage_label = QLabel("")
        self.usage_label.setStyleSheet(
            "font-size:12px; color:#1f2937; font-weight:600; "
            "background:#f3f4f6; border-radius:6px; padding:4px 10px;"
        )
        self.usage_label.setToolTip("Aggregate CPU and memory usage of running containers")
        self.usage_label.hide()

        layout.addWidget(self.state_dot)
        layout.addWidget(self.state_label)
        layout.addWidget(self.runtime_label)
        layout.addStretch(1)
        layout.addWidget(self.usage_label)

        # Indeterminate progress shown while a lifecycle operation runs.
        self._progress = QProgressBar(self)
        self._progress.setFixedWidth(80)
        self._progress.setMaximumHeight(4)
        self._progress.setMaximum(0)
        self._progress.setTextVisible(False)
        self._progress.hide()
        layout.addWidget(self._progress)
        layout.addSpacing(4)

        self.start_btn = QPushButton("▶  Start Colima")
        self.start_btn.setToolTip("Start the Colima virtual machine")
        self.start_btn.setMinimumWidth(132)
        self.start_btn.setStyleSheet(
            "QPushButton { background:#16a34a; color:#ffffff; border:none; "
            "border-radius:8px; padding:8px 18px; font-weight:700; font-size:13px; }"
            "QPushButton:hover { background:#15803d; }"
            "QPushButton:pressed { background:#166534; }"
            "QPushButton:disabled { background:#e5e7eb; color:#6b7280; }"
        )
        self.start_btn.clicked.connect(self._on_start)
        layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹  Stop Colima")
        self.stop_btn.setToolTip("Stop the Colima virtual machine")
        self.stop_btn.setMinimumWidth(132)
        self.stop_btn.setStyleSheet(
            "QPushButton { background:#4b5563; color:#ffffff; border:none; "
            "border-radius:8px; padding:8px 18px; font-weight:700; font-size:13px; }"
            "QPushButton:hover { background:#374151; }"
            "QPushButton:pressed { background:#1f2937; }"
            "QPushButton:disabled { background:#e5e7eb; color:#6b7280; }"
        )
        self.stop_btn.clicked.connect(self._on_stop)
        layout.addWidget(self.stop_btn)

        self.restart_btn = QPushButton("⟳  Restart")
        self.restart_btn.setToolTip("Restart the Colima virtual machine")
        self.restart_btn.setMinimumWidth(104)
        self.restart_btn.setStyleSheet(
            "QPushButton { background:#2563eb; color:#ffffff; border:none; "
            "border-radius:8px; padding:8px 16px; font-weight:700; font-size:13px; }"
            "QPushButton:hover { background:#1d4ed8; }"
            "QPushButton:pressed { background:#1e40af; }"
            "QPushButton:disabled { background:#e5e7eb; color:#6b7280; }"
        )
        self.restart_btn.clicked.connect(self._on_restart)
        layout.addWidget(self.restart_btn)

        self.refresh_btn = QPushButton("⟳  Refresh")
        self.refresh_btn.setToolTip(
            "Refresh containers, images, compose stacks, and profiles  (Ctrl/Cmd+R, F5)"
        )
        self.refresh_btn.setMinimumWidth(100)
        self.refresh_btn.setStyleSheet(
            "QPushButton { background:#f3f4f6; color:#374151; border:1px solid #d1d5db; "
            "border-radius:8px; padding:8px 14px; font-weight:600; font-size:13px; }"
            "QPushButton:hover { background:#e5e7eb; border-color:#9ca3af; }"
            "QPushButton:pressed { background:#d1d5db; }"
            "QPushButton:disabled { background:#f9fafb; color:#9ca3af; border-color:#e5e7eb; }"
        )
        self.refresh_btn.clicked.connect(self._on_refresh)
        layout.addWidget(self.refresh_btn)

        self._operation: Optional[str] = None
        self.set_state(False, None, None)

    def set_state(
        self, running: bool, runtime: Optional[str], error: Optional[str] = None
    ) -> None:
        # Don't overwrite an in-progress operation's indicator.
        if self._operation is not None:
            return
        self._progress.hide()
        engine_missing = self._app.engine is None
        if engine_missing:
            self.state_dot.setText("○")
            self.state_dot.setStyleSheet(
                "background:transparent; color:#999; border-radius:10px; "
                "font-size:16px; font-weight:bold; padding:0 3px;"
            )
            self.state_label.setText("Colima unavailable")
            self.runtime_label.setText("engine not found")
            self.usage_label.hide()
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.restart_btn.setEnabled(False)
            self.refresh_btn.setEnabled(True)
            self.state_label.setToolTip("Colima CLI not found")
            self.usage_label.hide()
        elif running:
            self.state_dot.setText("●")
            self.state_dot.setStyleSheet(
                "background:transparent; color:#228F48; border-radius:10px; "
                "font-size:16px; font-weight:bold; padding:0 3px;"
            )
            self.state_label.setText("Colima running")
            self.runtime_label.setText(f"runtime: {runtime or 'unknown'}")
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.restart_btn.setEnabled(True)
            self.refresh_btn.setEnabled(True)
            self.state_label.setToolTip("Colima is running")
        else:
            self.state_dot.setText("○")
            self.state_dot.setStyleSheet(
                "background:transparent; color:#999; border-radius:10px; "
                "font-size:16px; font-weight:bold; padding:0 3px;"
            )
            self.state_label.setText("Colima stopped")
            if error:
                self.runtime_label.setText((error or "").splitlines()[0][:60])
            else:
                self.runtime_label.setText("runtime: —")
            self.usage_label.hide()
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.restart_btn.setEnabled(False)
            self.refresh_btn.setEnabled(True)
            self.state_label.setToolTip(error or "Colima is stopped")
            self.usage_label.hide()

    def set_operation(self, name: str) -> None:
        self._operation = name
        label = {
            "start": "Starting Colima…",
            "stop": "Stopping Colima…",
            "restart": "Restarting Colima…",
        }.get(name, f"{name}…")
        self.state_dot.setText("⏳")
        self.state_dot.setStyleSheet(
            "background:transparent; color:#f59e0b; font-size:16px; font-weight:bold; padding:0 3px;"
        )
        self.state_label.setText(label)
        self.runtime_label.setText("please wait")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.restart_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self._progress.show()

    def clear_operation(self) -> None:
        self._operation = None
        self._progress.hide()
        # Restore the badge from the controller's latest known state.
        app_state = getattr(self._app, "state", None)
        if app_state is not None:
            self.set_state(
                bool(app_state.running), app_state.runtime, app_state.error
            )

    def set_usage(self, cpu: str, mem: str) -> None:
        # Always keep the badge visible while Colima is running; show dashes
        # instead of hiding so the readout never blinks/disappears.
        cpu = cpu or "—"
        mem = mem or "—"
        self.usage_label.setText(f"CPU {cpu} · RAM {mem}")
        self.usage_label.show()
