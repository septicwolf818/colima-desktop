"""Dialogs used by Colima Desk: logs viewers, profile editor, settings."""

from __future__ import annotations

import html as _html
import re as _re

from typing import Callable, List, Optional

from PySide6.QtCore import Qt, QTimer, QThread, Signal as _Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from .fonts import _MONO_FAMILY, _mono_font


def _to_int(value, default: int) -> int:
    """Parse an int, tolerating unit suffixes like ``100GiB``."""
    try:
        return int(float(str(value).strip().rstrip("GiB")))
    except (TypeError, ValueError):
        return default


def _to_float(value, default: float) -> float:
    """Parse a float, tolerating unit suffixes like ``2GiB``."""
    try:
        return float(str(value).strip().rstrip("GiB"))
    except (TypeError, ValueError):
        return default


# ── ANSI → HTML ─────────────────────────────────────────────────────────────

_ANSI_COLORS = {
    30: "#000000", 31: "#cd3131", 32: "#0dbc79", 33: "#e5e510",
    34: "#2472c8", 35: "#bc3fbc", 36: "#11a8cd", 37: "#e5e5e5",
    90: "#666666", 91: "#f14c4c", 92: "#23d18b", 93: "#f5f543",
    94: "#3b8eea", 95: "#d670d6", 96: "#29b8db", 97: "#e5e5e5",
}
_ANSI_BG = {
    40: "#000000", 41: "#cd3131", 42: "#0dbc79", 43: "#e5e510",
    44: "#2472c8", 45: "#bc3fbc", 46: "#11a8cd", 47: "#e5e5e5",
    100: "#666666", 101: "#f14c4c", 102: "#23d18b", 103: "#f5f543",
    104: "#3b8eea", 105: "#d670d6", 106: "#29b8db", 107: "#e5e5e5",
}


_TS_RE = _re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?")

# 16-color palette for compose service names (modulo service index).
_SERVICE_PALETTE = [
    "\033[36m", "\033[33m", "\033[35m", "\033[34m",
    "\033[32m", "\033[31m", "\033[96m", "\033[93m",
    "\033[95m", "\033[94m", "\033[92m", "\033[91m",
    "\033[37m", "\033[90m", "\033[97m", "\033[38;5;214m",
]
_RESET = "\033[0m"


def _extract_ts(line: str) -> str:
    m = _TS_RE.search(line)
    return m.group(0) if m else ""


def sort_log_lines(body: str) -> str:
    """Sort log lines by their embedded timestamp (if any)."""
    lines = body.splitlines()
    keyed = []
    for i, line in enumerate(lines):
        ts = _extract_ts(line)
        # Timestamped lines sort by ts; others keep original order at the end.
        key = (0, ts, i) if ts else (1, "", i)
        keyed.append((key, line))
    keyed.sort(key=lambda x: x[0])
    return "\n".join(line for _, line in keyed)


def ansi_to_html(text: str) -> str:
    """Convert ANSI escape sequences in *text* to HTML spans."""
    # Strip other CSI sequences (cursor moves, erase line, etc.).
    text = _re.sub(r"\x1b\[[0-9;]*[A-Za-z]", _replace_sgr, text)
    # Escape HTML special chars in the remaining text.
    # But we already inserted tags; need to escape only non-tag text.
    # Approach: split on tags, escape text parts.
    return _escape_text_outside_tags(text)


def _replace_sgr(match: "_re.Match") -> str:
    seq = match.group(0)
    m = _re.fullmatch(r"\x1b\[(\d+(?:;\d+)*)m", seq)
    if not m:
        # Non-SGR CSI: drop it.
        return ""
    codes = [int(x) for x in m.group(1).split(";")] if m.group(1) else [0]
    if codes == [0] or 0 in codes:
        return "</span>"
    out = ""
    fg = None
    bg = None
    bold = False
    for code in codes:
        if code == 1:
            bold = True
        elif code in _ANSI_COLORS:
            fg = _ANSI_COLORS[code]
        elif code in _ANSI_BG:
            bg = _ANSI_BG[code]
        elif code == 39:
            fg = None
        elif code == 49:
            bg = None
    style = ""
    if fg:
        style += f"color:{fg};"
    if bg:
        style += f"background-color:{bg};"
    if bold:
        style += "font-weight:bold;"
    if style:
        return f'<span style="{style}">'
    return ""


def _escape_text_outside_tags(text: str) -> str:
    """HTML-escape text while preserving our inserted <span> tags."""
    # Split keeping tags.
    parts = _re.split(r"(<[^>]+>)", text)
    out = []
    for part in parts:
        if part.startswith("<") and part.endswith(">"):
            out.append(part)
        else:
            out.append(_html.escape(part))
    return "".join(out)


class LogStreamer(QThread):
    """Stream `docker logs -f` (or compose equivalent) line by line."""

    line = _Signal(str)

    def __init__(self, cmd: List[str], env=None, parent=None) -> None:
        super().__init__(parent)
        self._cmd = cmd
        self._env = env
        self._proc = None
        self._stop = False

    def run(self) -> None:
        import subprocess, os
        run_env = None
        if self._env:
            run_env = dict(os.environ)
            run_env.update(self._env)
        try:
            self._proc = subprocess.Popen(
                self._cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=run_env,
            )
            for raw in self._proc.stdout:
                if self._stop:
                    break
                self.line.emit(raw)
            try:
                self._proc.wait(timeout=5)
            except Exception:
                pass
        except Exception as exc:
            self.line.emit(f"\x1b[31m[stream error: {exc}] — live stream stopped, falling back to polling\x1b[0m\n")
        finally:
            if self._proc is not None:
                try:
                    self._proc.terminate()
                except Exception:
                    pass

    def stop(self) -> None:
        self._stop = True
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass


class LogsDialog(QDialog):
    """Scrollable log viewer with optional service selector, follow mode, and
    newest-first ordering."""

    def __init__(
        self,
        app,
        title: str,
        fetch: Callable[[Optional[str], object], None],
        services: Optional[List[str]] = None,
        tail: object = 1000,
        container_name: Optional[str] = None,
        compose_config: Optional[str] = None,
    ) -> None:
        super().__init__(app.window)
        self._app = app
        self._fetch_fn = fetch
        self._services = services or []
        self._tail = tail
        self._current_tail = tail
        self._last_body = None
        self._streamer = None
        self._streaming = False
        # Preserve values set by a subclass before super().__init__().
        if container_name is not None:
            self._container_name = container_name
        elif not hasattr(self, "_container_name"):
            self._container_name = None
        if compose_config is not None:
            self._compose_config = compose_config
        elif not hasattr(self, "_compose_config"):
            self._compose_config = None
        # Persistent color map for compose service-name prefixes.
        if not hasattr(self, "_prefix_colors"):
            self._prefix_colors = {}
            self._next_color_idx = 0
        self.setWindowTitle(title)
        self.resize(900, 580)
        self.setMinimumSize(600, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)

        # ── controls row ─────────────────────────────────────────────────
        row = QHBoxLayout()
        row.setSpacing(8)
        if self._services:
            row.addWidget(QLabel("Service:"))
            self._selector = QComboBox()
            self._selector.addItem("All services", None)
            seen = set()
            for svc in self._services:
                if svc in seen:
                    continue
                seen.add(svc)
                self._selector.addItem(svc, svc)
            row.addWidget(self._selector, 1)
            self._selector.currentIndexChanged.connect(lambda _: self._fetch())
        else:
            self._selector = None
            row.addStretch(1)

        self._follow = QCheckBox("Follow live output")
        self._follow.setToolTip("Stream new log lines as they are written")
        self._follow.setStyleSheet("font-weight:600;")
        self._follow.toggled.connect(self._on_follow_toggled)
        row.addWidget(self._follow)

        self._refresh_btn = QPushButton("⟳ Refresh")
        self._refresh_btn.setToolTip("Reload the current log view")
        self._refresh_btn.clicked.connect(lambda: self._fetch())
        row.addWidget(self._refresh_btn)

        self._load_all_btn = QPushButton("Load all")
        self._load_all_btn.setToolTip("Load the entire log history")
        self._load_all_btn.clicked.connect(lambda: self._fetch(tail="all"))
        row.addWidget(self._load_all_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setToolTip("Clear the log view")
        self._clear_btn.clicked.connect(self._clear)
        row.addWidget(self._clear_btn)
        layout.addLayout(row)

        # ── log view ─────────────────────────────────────────────────────
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(_mono_font())
        self._text.setStyleSheet(
            "background:#1e1e1e; color:#d4d4d4; border:none; border-radius:6px;"
        )
        self._text.setPlaceholderText("No log output yet…")
        layout.addWidget(self._text, 1)

        # ── buttons ──────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._fetch)

        self._fetch()
        # Default to live streaming (unchecks itself if streaming is unavailable).
        self._follow.setChecked(True)

    # ── follow / streaming ─────────────────────────────────────────────────

    def _on_follow_toggled(self, checked: bool) -> None:
        if checked:
            self._start_stream()
            if not self._streaming:
                # Streaming is not possible (e.g. no runtime CLI) — reflect
                # that in the checkbox instead of leaving it falsely checked.
                self._follow.blockSignals(True)
                self._follow.setChecked(False)
                self._follow.blockSignals(False)
        else:
            self._stop_stream()

    def _build_stream_cmd(self, cli: str, service):
        if self._compose_config:
            cmd = [cli, "compose", "-f", self._compose_config, "logs", "-f",
                   "--timestamps", "--tail", "0"]
            if service:
                cmd.append(service)
            return cmd
        if self._container_name:
            return [cli, "logs", "-f", "--timestamps", "--tail", "0",
                    self._container_name]
        return None

    def _start_stream(self) -> None:
        self._stop_stream()
        cli = None
        if self._app.engine is not None:
            cli = self._app.engine.container_service.cli("docker")
        if cli is None:
            self._timer.start()
            return
        service = self._selector.currentData() if self._selector is not None else None
        cmd = self._build_stream_cmd(cli, service)
        if cmd is None:
            self._timer.start()
            return
        env = None
        if self._app.engine is not None:
            sock = self._app.engine.docker_socket()
            if sock:
                env = {"DOCKER_HOST": sock}
        self._streaming = True
        self._streamer = LogStreamer(cmd, env=env, parent=self)
        self._streamer.line.connect(self._on_stream_line)
        self._streamer.finished.connect(self._on_stream_finished)
        self._streamer.start()

    def _stop_stream(self) -> None:
        self._streaming = False
        if self._streamer is not None:
            self._streamer.stop()
            self._streamer.wait(3000)
            self._streamer = None
        self._timer.stop()

    def _on_stream_line(self, line: str) -> None:
        sb = self._text.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        if self._services:
            line = self._colorize_line(line)
        html = ansi_to_html(line.rstrip("\r\n"))
        self._text.append(
            f'<span style="font-family:{_MONO_FAMILY}; font-size:11pt; '
            f'white-space:pre-wrap;">{html}</span>'
        )
        if at_bottom:
            sb.setValue(sb.maximum())

    def _on_stream_finished(self) -> None:
        self._streamer = None
        if self._streaming:
            self._streaming = False
            # The stream ended (e.g. the container stopped); reflect that in
            # the checkbox and fall back to polling so the view still updates.
            self._follow.blockSignals(True)
            self._follow.setChecked(False)
            self._follow.blockSignals(False)
            self._timer.start()

    def _colorize_line(self, line: str) -> str:
        """Color a single compose log line's service prefix, using a persistent
        color map so colors stay consistent across streamed lines."""
        m = _re.match(r"^(\S+)(\s*\|)", line)
        if not m:
            return line
        prefix = m.group(1)
        if prefix not in self._prefix_colors:
            self._prefix_colors[prefix] = _SERVICE_PALETTE[
                self._next_color_idx % len(_SERVICE_PALETTE)
            ]
            self._next_color_idx += 1
        color = self._prefix_colors[prefix]
        idx = line.find("|")
        if idx >= 0:
            return f"{color}{line[:idx]}{_RESET}{line[idx:]}"
        return line

    def _colorize_body(self, body: str) -> str:
        """Color all service prefixes in a full log body, using and updating
        the persistent color map."""
        for line in body.splitlines():
            m = _re.match(r"^(\S+)(\s*\|)", line)
            if m:
                prefix = m.group(1)
                if prefix not in self._prefix_colors:
                    self._prefix_colors[prefix] = _SERVICE_PALETTE[
                        self._next_color_idx % len(_SERVICE_PALETTE)
                    ]
                    self._next_color_idx += 1
        out = []
        for line in body.splitlines(keepends=True):
            m = _re.match(r"^(\S+)(\s*\|)", line)
            if m:
                prefix = m.group(1)
                color = self._prefix_colors.get(prefix)
                if color is not None:
                    idx = line.find("|")
                    if idx >= 0:
                        line = f"{color}{line[:idx]}{_RESET}{line[idx:]}"
            out.append(line)
        return "".join(out)

    # ── fetching ───────────────────────────────────────────────────────────

    def _clear(self) -> None:
        self._text.clear()
        self._last_body = None

    def _fetch(self, tail=None) -> None:
        # Preserve the follow state before stopping any stream so we can
        # restore it after the fetch completes.
        self._was_following = self._follow.isChecked()
        # Manual refresh: stop streaming first.
        if self._streaming:
            self._stop_stream()
            self._follow.blockSignals(True)
            self._follow.setChecked(False)
            self._follow.blockSignals(False)
        t = tail if tail is not None else self._current_tail
        self._current_tail = t
        self._load_all_btn.setEnabled(t != "all")
        service = self._selector.currentData() if self._selector is not None else None
        self._app.set_logs_handler(self._on_logs)
        self._fetch_fn(service, t)

    def _on_logs(self, result) -> None:
        self._app.set_logs_handler(None)
        if result.success:
            body = result.stdout or ""
            if result.stderr:
                body = body + "\n--- stderr ---\n" + result.stderr
        else:
            body = f"Error: {result.message}"
        if self._services:
            body = self._colorize_body(body)
        body = sort_log_lines(body or "(no logs)")
        # Skip redundant updates to avoid flicker — but still restore follow.
        if body == self._last_body:
            # Restore follow state before returning.
            if getattr(self, "_was_following", False):
                del self._was_following
                self._follow.setChecked(True)
                self._on_follow_toggled(True)
            return
        self._last_body = body
        sb = self._text.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        html_body = ansi_to_html(body)
        self._text.setHtml(
            f'<pre style="font-family:{_MONO_FAMILY}; font-size:11pt; '
            f'white-space:pre-wrap; margin:0;">{html_body}</pre>'
        )
        # Only auto-scroll to the bottom if the user was already at the
        # bottom. If they scrolled up to read older lines, leave the scroll
        # position alone so we never yank them back.
        if at_bottom:
            sb.setValue(sb.maximum())

        # Restore follow state that was active before the fetch (e.g. "Load
        # All" temporarily disables streaming; restore it when done).
        if getattr(self, "_was_following", False):
            del self._was_following
            self._follow.setChecked(True)
            self._on_follow_toggled(True)

    def closeEvent(self, event) -> None:
        self._timer.stop()
        self._stop_stream()
        super().closeEvent(event)

    def reject(self) -> None:
        self._timer.stop()
        self._stop_stream()
        super().reject()

    def accept(self) -> None:
        self._timer.stop()
        self._stop_stream()
        super().accept()


class ComposeLogsDialog(LogsDialog):
    """Logs viewer for a compose stack (all services or one)."""

    def __init__(self, app, project) -> None:
        self._compose_config = project.config_files
        services = []
        seen = set()
        for c in project.containers:
            svc = c.service or c.name
            if svc not in seen:
                seen.add(svc)
                services.append(svc)

        def fetch(service, tail=1000):
            app.compose_logs(project.config_files, service, tail)

        super().__init__(
            app, f"Compose Logs — {project.name}", fetch, services,
            compose_config=project.config_files,
        )


class ContainerLogsDialog(LogsDialog):
    """Logs viewer for a single container."""

    def __init__(self, app, container_name: str, tail: object = 1000) -> None:
        def fetch(_service, t=1000):
            app.show_logs(container_name, t)  # reuses container logs path

        super().__init__(
            app, f"Container Logs — {container_name}", fetch, None, tail,
            container_name=container_name,
        )


# ── profile editor / settings ───────────────────────────────────────────────


class ProfileEditorDialog(QDialog):
    """Edit a Colima profile's resource settings (cpu/memory/disk/k8s)."""

    def __init__(self, app, profile) -> None:
        super().__init__(app.window)
        self._app = app
        self._profile = profile
        self.setWindowTitle(f"Edit Profile — {profile.name}")
        self.resize(440, 400)
        self.setMinimumSize(420, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        info = QLabel(
            f"Profile: {profile.name}  ·  Status: {profile.status}  ·  "
            f"Runtime: {profile.runtime}"
        )
        info.setStyleSheet("color:#555; font-size:12px; background:transparent;")
        layout.addWidget(info)

        form = QFormLayout()
        form.setSpacing(8)

        cfg = app.engine.read_profile_config(profile.name) if app.engine else {}

        self._cpu = QSpinBox()
        self._cpu.setRange(1, 64)
        self._cpu.setValue(_to_int(cfg.get("cpu", profile.cpus or 2), 2))
        form.addRow("CPUs:", self._cpu)

        self._memory = QDoubleSpinBox()
        self._memory.setRange(1, 128)
        self._memory.setDecimals(1)
        self._memory.setValue(
            _to_float(cfg.get("memory", profile.memory or "2"), 2.0)
        )
        form.addRow("Memory (GiB):", self._memory)

        self._disk = QSpinBox()
        self._disk.setRange(1, 1024)
        self._disk.setValue(_to_int(cfg.get("disk", profile.disk or "100"), 100))
        form.addRow("Disk (GiB):", self._disk)

        self._k8s = QCheckBox("Enable Kubernetes")
        self._k8s.setChecked(
            str(cfg.get("kubernetes", "false")).lower() in ("true", "yes", "1")
        )
        form.addRow("", self._k8s)

        arch_edit = QLineEdit(cfg.get("arch", profile.arch or ""))
        arch_edit.setReadOnly(True)
        form.addRow("Arch (read-only):", arch_edit)

        runtime_edit = QLineEdit(cfg.get("runtime", profile.runtime or ""))
        runtime_edit.setReadOnly(True)
        form.addRow("Runtime (read-only):", runtime_edit)

        layout.addLayout(form)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet(
            "color:#dc2626; font-size:12px; background:transparent;"
        )
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        note = QLabel(
            "Note: changes apply on next start (stop then start the profile). "
            "Arch/runtime cannot be changed after creation."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#888; font-size:11pt; background:transparent;")
        layout.addWidget(note)
        layout.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save")

        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        self._cpu.setFocus()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(bool(message))

    def _save(self) -> None:
        values = {
            "cpu": self._cpu.value(),
            "memory": self._memory.value(),
            "disk": self._disk.value(),
            "kubernetes": "true" if self._k8s.isChecked() else "false",
        }
        if self._app.engine is not None:
            res = self._app.engine.write_profile_config(self._profile.name, values)
            if not res.success:
                self._show_error(res.message)
                return
            # Apply the new settings by restarting the profile (if running)
            # or starting it (if stopped), so the list reflects the change.
            if self._profile.running:
                self._app.restart_profile(self._profile.name)
            else:
                self._app.start_profile(self._profile.name)
        self.accept()


class SettingsDialog(QDialog):
    """Application settings: edit a profile's resources + start args."""

    def __init__(self, app) -> None:
        super().__init__(app.window)
        self._app = app
        self.setWindowTitle("Settings")
        self.resize(480, 500)
        self.setMinimumSize(440, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        prof_row = QHBoxLayout()
        prof_row.addWidget(QLabel("Profile:"))
        self._profile_combo = QComboBox()
        self._profile_combo.addItem("Loading…")
        self._profile_combo.setEnabled(False)
        prof_row.addWidget(self._profile_combo, 1)
        layout.addLayout(prof_row)

        form = QFormLayout()
        form.setSpacing(8)

        self._cpu = QSpinBox()
        self._cpu.setRange(1, 64)
        self._cpu.setValue(2)
        form.addRow("CPUs:", self._cpu)

        self._memory = QDoubleSpinBox()
        self._memory.setRange(1, 128)
        self._memory.setDecimals(1)
        self._memory.setValue(2)
        form.addRow("Memory (GiB):", self._memory)

        self._disk = QSpinBox()
        self._disk.setRange(1, 1024)
        self._disk.setValue(100)
        form.addRow("Disk (GiB):", self._disk)

        self._k8s = QCheckBox("Enable Kubernetes")
        form.addRow("", self._k8s)

        arch_edit = QLineEdit()
        arch_edit.setReadOnly(True)
        form.addRow("Arch (read-only):", arch_edit)
        self._arch_edit = arch_edit

        runtime_edit = QLineEdit()
        runtime_edit.setReadOnly(True)
        form.addRow("Runtime (read-only):", runtime_edit)
        self._runtime_edit = runtime_edit

        layout.addLayout(form)

        layout.addWidget(
            QLabel("Start options (extra args for `colima start`):")
        )
        self._start_args = QLineEdit(" ".join(app.config.start_args))
        self._start_args.setPlaceholderText("e.g. --cpu 4 --memory 8")
        layout.addWidget(self._start_args)

        self._args_error = QLabel("")
        self._args_error.setStyleSheet(
            "color:#dc2626; font-size:12px; background:transparent;"
        )
        self._args_error.setWordWrap(True)
        self._args_error.setVisible(False)
        layout.addWidget(self._args_error)

        self._auto_start = QCheckBox(
            "Start Colima automatically when the app launches"
        )
        self._auto_start.setChecked(app.config.auto_start_colima)
        layout.addWidget(self._auto_start)

        note = QLabel(
            "Profile changes apply on next start (stop then start). "
            "Arch/runtime cannot be changed after creation."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#888; font-size:11pt; background:transparent;")
        layout.addWidget(note)
        layout.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save")

        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        self._start_args.textChanged.connect(lambda _: self._clear_args_error())
        self._profile_combo.currentIndexChanged.connect(self._reload_profile)
        self._load_profiles()
        self._start_args.setFocus()

    # ── profile loading ────────────────────────────────────────────────────

    def _load_profiles(self) -> None:
        """Populate the profile combo off the UI thread."""
        if self._app.engine is None:
            self._profile_combo.clear()
            self._profile_combo.addItem(self._app.config.default_profile)
            self._profile_combo.setEnabled(True)
            self._reload_profile()
            return

        def _do():
            return self._app.engine.list_profiles()

        def _on_done(profiles):
            self._profile_combo.blockSignals(True)
            self._profile_combo.clear()
            for p in profiles:
                self._profile_combo.addItem(p.name, p)
            self._profile_combo.blockSignals(False)
            self._profile_combo.setEnabled(True)
            idx = self._profile_combo.findText(self._app.config.default_profile)
            if idx >= 0:
                self._profile_combo.setCurrentIndex(idx)
            self._reload_profile()

        def _on_err(_):
            self._profile_combo.blockSignals(True)
            self._profile_combo.clear()
            self._profile_combo.addItem(self._app.config.default_profile)
            self._profile_combo.blockSignals(False)
            self._profile_combo.setEnabled(True)
            self._reload_profile()

        self._app.run(_do, _on_done, _on_err)

    def _reload_profile(self) -> None:
        if self._app.engine is None:
            self._arch_edit.setText("")
            self._runtime_edit.setText("")
            return
        name = self._profile_combo.currentText()
        cfg = self._app.engine.read_profile_config(name)
        try:
            self._cpu.setValue(int(cfg.get("cpu", 2)))
        except (TypeError, ValueError):
            pass
        try:
            self._memory.setValue(float(cfg.get("memory", 2)))
        except (TypeError, ValueError):
            pass
        try:
            self._disk.setValue(int(cfg.get("disk", 100)))
        except (TypeError, ValueError):
            pass
        self._k8s.setChecked(
            str(cfg.get("kubernetes", "false")).lower() in ("true", "yes", "1")
        )
        self._arch_edit.setText(str(cfg.get("arch", "")))
        self._runtime_edit.setText(str(cfg.get("runtime", "")))

    # ── saving ──────────────────────────────────────────────────────────────

    def _clear_args_error(self) -> None:
        self._args_error.setVisible(False)
        self._args_error.setText("")

    def _show_args_error(self, message: str) -> None:
        self._args_error.setText(message)
        self._args_error.setVisible(bool(message))

    def _save(self) -> None:
        import shlex

        name = self._profile_combo.currentText()
        if not name or name == "Loading…":
            self._show_args_error("Profiles are still loading; try again in a moment.")
            return

        try:
            args = shlex.split(self._start_args.text())
        except ValueError as exc:
            self._show_args_error(f"Invalid start options: {exc}")
            return

        values = {
            "cpu": self._cpu.value(),
            "memory": self._memory.value(),
            "disk": self._disk.value(),
            "kubernetes": "true" if self._k8s.isChecked() else "false",
        }
        profile_running = False
        if self._app.engine is not None:
            prof = self._profile_combo.currentData()
            profile_running = bool(prof and prof.running)
            res = self._app.engine.write_profile_config(name, values)
            if not res.success:
                self._show_args_error(res.message)
                return
            # Apply the new settings by restarting (if running) or starting.
            if profile_running:
                self._app.restart_profile(name)
            else:
                self._app.start_profile(name)

        self._app.update_start_args(args)
        self._app.config.default_profile = name
        if self._app.engine is not None:
            self._app.engine._state_profile = name
        self._app.config.auto_start_colima = self._auto_start.isChecked()
        self._app.save_config()
        self.accept()
