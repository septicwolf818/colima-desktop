"""Top-level application controller.

Owns the engine, config, main window and tray, and coordinates background
work (via Worker threads) + UI updates. Pure application logic, no Qt
widget code of its own beyond signals.
"""

from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtCore import QObject, Signal

from .config import ColimaConfig, ColimaConfigStore
from .engine import ColimaEngine, EngineError
from .gui.async_worker import Worker
from .models import ColimaState, Container, ContainerStat, Image, OperationResult, Profile


_MEM_UNITS = {"b": 1, "kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4,
              "kb": 1000, "mb": 1000**2, "gb": 1000**3, "tb": 1000**4}


def _parse_mem_bytes(s: str):
    """Parse a memory string like '540KiB' or '1.5MiB' into bytes, or None."""
    s = s.strip()
    if not s:
        return None
    # Split numeric part from unit.
    i = 0
    while i < len(s) and (s[i].isdigit() or s[i] in "."):
        i += 1
    num_part = s[:i].strip()
    unit_part = s[i:].strip().lower()
    if not num_part:
        return None
    try:
        val = float(num_part)
    except ValueError:
        return None
    mult = _MEM_UNITS.get(unit_part, 1)
    return val * mult


def _format_bytes(b: float) -> str:
    if b >= 1024**3:
        return f"{b / 1024**3:.2f} GiB"
    if b >= 1024**2:
        return f"{b / 1024**2:.1f} MiB"
    if b >= 1024:
        return f"{b / 1024:.0f} KiB"
    return f"{b:.0f} B"


class ColimaDeskApp(QObject):
    # ── signals ────────────────────────────────────────────────────────────
    state_changed = Signal(ColimaState)
    app_log = Signal(str)  # application-level log line
    operation_started = Signal(str)
    operation_output = Signal(str, str)  # operation name, output line
    operation_done = Signal(str, OperationResult)
    containers_loaded = Signal(list, dict)  # refs, stats dict
    images_loaded = Signal(list)
    profiles_loaded = Signal(list)
    compose_projects_loaded = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._window = None
        self._tray = None
        self._logs_dialog = None
        self._logs_handler = None
        self._pending_logs: List[str] = []
        self._auto_start_attempted: bool = False
        self._initial_refresh: bool = True
        self._stats_in_flight: bool = False
        self._state: ColimaState = ColimaState()
        self._state_profile = None
        self._workers: List[Worker] = []

        self.config = ColimaConfigStore.load()
        self._state_profile = self.config.default_profile
        try:
            self.engine = ColimaEngine()
        except EngineError as exc:
            # Engine may be unavailable; keep going so the UI can show an error.
            self.engine = None
            self._engine_error = str(exc)
            self.log(f"\x1b[31mEngine not found: {exc}\x1b[0m")
        else:
            self.engine._state_profile = self.config.default_profile
            self._engine_error = None
            try:
                profiles = self.engine.list_profiles()
                names = {p.name for p in profiles}
                if self.config.default_profile not in names and names:
                    self.log(f"\x1b[33mConfigured default profile '{self.config.default_profile}' not found; falling back to 'default'.\x1b[0m")
                    self.config.default_profile = "default"
                    self.engine._state_profile = "default"
                    self.save_config()
            except Exception:
                pass
            self.log(f"\x1b[32mColima Desktop started. Colima CLI: {self.engine.cli_path}\x1b[0m")

    # ── wiring ────────────────────────────────────────────────────────────

    def attach_window(self, window) -> None:
        self._window = window
        # Flush any logs emitted before the window was attached.
        for msg in self._pending_logs:
            self.app_log.emit(msg)
        self._pending_logs.clear()

    def attach_tray(self, tray) -> None:
        self._tray = tray

    def log(self, msg: str) -> None:
        """Emit an application-level log line (buffered until window attaches)."""
        if self._window is None:
            self._pending_logs.append(msg)
        else:
            self.app_log.emit(msg)

    @property
    def window(self):
        return self._window

    @property
    def tray(self):
        return self._tray

    @property
    def colima_running(self) -> bool:
        return bool(self._state and self._state.running)

    @property
    def state(self) -> ColimaState:
        return self._state

    # ── async helper ──────────────────────────────────────────────────────

    def run(self, fn, on_done, on_error) -> Worker:
        """Run *fn* on a worker thread, delivering results to the main thread."""
        w = Worker(fn)
        w.done.connect(on_done)
        w.error.connect(on_error)
        w.finished.connect(lambda w=w: self._cleanup_worker(w))
        self._workers.append(w)
        w.start()
        return w

    def _cleanup_worker(self, w: Worker) -> None:
        if w in self._workers:
            self._workers.remove(w)

    def _fail(self, msg: str) -> OperationResult:
        return OperationResult(success=False, stderr=msg, returncode=1)

    # ── state + refresh ───────────────────────────────────────────────────

    def refresh_state(self) -> None:
        if self.engine is None:
            self._state = ColimaState(running=False, error=self._engine_error)
            self.state_changed.emit(self._state)
            # Nothing can be listed without an engine.
            self.containers_loaded.emit([], {})
            self.images_loaded.emit([])
            self.compose_projects_loaded.emit([])
            return

        def _do():
            return self.engine.get_state(), self.engine.version()

        def _on_done(res):
            state, version = res
            state.version = version
            self._state = state
            self.state_changed.emit(state)
            if self._tray is not None:
                self._tray.update_state(state)
            # Log state transitions (only when changed).
            if not hasattr(self, "_last_running") or self._last_running != state.running:
                self._last_running = state.running
                if state.running:
                    self.log(f"\x1b[32mColima: running (runtime: {state.runtime or 'unknown'})\x1b[0m")
                else:
                    self.log(f"\x1b[33mColima: stopped\x1b[0m")
            # Auto-start Colima on app launch if enabled and currently stopped.
            if (
                self._initial_refresh
                and self.config.auto_start_colima
                and not state.running
                and not self._auto_start_attempted
                and self.engine is not None
            ):
                self._auto_start_attempted = True
                self.log("\x1b[36mAuto-start enabled: starting Colima…\x1b[0m")
                self.start_profile()
            self._initial_refresh = False
            # Keep the container/image lists (and compose stacks) in sync with
            # the running state so the UI reflects starts/stops automatically.
            if state.running:
                self.refresh_containers()
                self.refresh_images()
                self.refresh_compose_projects()
                self.refresh_container_stats()
            else:
                # Clear the lists so the panels can show a friendly
                # "Colima is not running" empty state instead of stale rows.
                self.containers_loaded.emit([], {})
                self.images_loaded.emit([])
                self.compose_projects_loaded.emit([])



        def _on_err(err):
            self._state = ColimaState(running=False, error=str(err))
            self.state_changed.emit(self._state)
            if self._tray is not None:
                self._tray.update_state(self._state)
 
        self.run(_do, _on_done, _on_err)

    def refresh_containers(self) -> None:
        if self.engine is None:
            return

        def _do():
            refs = self.engine.container_service.list()
            stats = self.engine.container_service.stats()
            stat_map = {s.id[:12]: s for s in stats}
            stat_map.update({s.id: s for s in stats})
            stat_map.update({s.name: s for s in stats})
            return refs, stat_map

        def _on_done(res):
            refs, stat_map = res
            self.containers_loaded.emit(refs, stat_map)

        def _on_err(err):
            self.containers_loaded.emit([], {})

        self.run(_do, _on_done, _on_err)

    def refresh_images(self) -> None:
        if self.engine is None:
            return

        def _do():
            return self.engine.image_service.list()

        def _on_done(res):
            self.images_loaded.emit(res)

        def _on_err(_):
            self.images_loaded.emit([])

        self.run(_do, _on_done, _on_err)

    def refresh_profiles(self) -> None:
        if self.engine is None:
            return

        def _do():
            return self.engine.list_profiles()

        def _on_done(res):
            self.profiles_loaded.emit(res)

        def _on_err(_):
            self.profiles_loaded.emit([])

        self.run(_do, _on_done, _on_err)

    def refresh_compose_projects(self) -> None:
        if self.engine is None:
            return

        def _do():
            return self.engine.container_service.list_compose_projects()

        def _on_done(res):
            self.compose_projects_loaded.emit(res)

        def _on_err(_):
            self.compose_projects_loaded.emit([])

        self.run(_do, _on_done, _on_err)

    def refresh_container_stats(self) -> None:
        if self.engine is None:
            return
        # Don't fetch stats (or touch the usage badge) while Colima is stopped;
        # otherwise the badge blinks between shown/hidden.
        if not getattr(self._state, "running", False):
            return
        if self._stats_in_flight:
            return
        self._stats_in_flight = True

        def _do():
            stats = self.engine.container_service.stats()
            cpu = "—"
            mem = "—"
            if stats:
                try:
                    cpu_val = sum(float(s.cpu.rstrip("%")) for s in stats if s.cpu.endswith("%"))
                    cpu = f"{cpu_val:.1f}%"
                except ValueError:
                    cpu = stats[0].cpu
                # Aggregate actual memory usage across all running containers.
                total_bytes = 0.0
                parsed = 0
                for s in stats:
                    usage_str = (s.memory or "").split("/")[0].strip()
                    val = _parse_mem_bytes(usage_str)
                    if val is not None:
                        total_bytes += val
                        parsed += 1
                if parsed:
                    mem = _format_bytes(total_bytes)
                elif stats:
                    mem = stats[0].memory
            return {"cpu": cpu, "mem": mem}

        def _on_done(res):
            self._stats_in_flight = False
            if self._window is not None:
                self._window.top_bar.set_usage(res["cpu"], res["mem"])

        def _on_err(_):
            self._stats_in_flight = False

        self.run(_do, _on_done, _on_err)

    def refresh_all(self) -> None:
        self.refresh_state()
        self.refresh_profiles()
        self.refresh_containers()
        self.refresh_images()
        self.refresh_compose_projects()

    # ── lifecycle ops ─────────────────────────────────────────────────────

    def _after_op(self, name: str, result: OperationResult, refresh: bool = True) -> None:
        self.operation_done.emit(name, result)
        if refresh:
            self.refresh_all()

    def start_profile(self, name: Optional[str] = None, args: Optional[List[str]] = None) -> None:
        if self.engine is None:
            self._after_op("start", self._fail(self._engine_error or "engine unavailable"), refresh=False)
            return
        profile = name or self.config.default_profile
        self.operation_started.emit("start")

        def _do():
            return self.engine.start(
                profile, args or self.config.start_args,
                on_line=lambda line: self.operation_output.emit("start", line),
            )

        def _on_done(res):
            self._after_op("start", res)

        self.run(_do, _on_done, lambda e: self._after_op("start", self._fail(str(e))))

    def stop_profile(self, name: Optional[str] = None) -> None:
        if self.engine is None:
            self._after_op("stop", self._fail(self._engine_error or "engine unavailable"), refresh=False)
            return
        profile = name or self.config.default_profile
        self.operation_started.emit("stop")

        def _do():
            return self.engine.stop(
                profile, on_line=lambda line: self.operation_output.emit("stop", line),
            )

        def _on_done(res):
            self._after_op("stop", res)

        self.run(_do, _on_done, lambda e: self._after_op("stop", self._fail(str(e))))

    def restart_profile(self, name: Optional[str] = None) -> None:
        if self.engine is None:
            self._after_op("restart", self._fail(self._engine_error or "engine unavailable"), refresh=False)
            return
        profile = name or self.config.default_profile
        self.operation_started.emit("restart")

        def _do():
            return self.engine.restart(
                profile, on_line=lambda line: self.operation_output.emit("restart", line),
            )

        def _on_done(res):
            self._after_op("restart", res)

        self.run(_do, _on_done, lambda e: self._after_op("restart", self._fail(str(e))))

    def delete_profile(self, name: str) -> None:
        if self.engine is None:
            self._after_op("delete profile", self._fail(self._engine_error or "engine unavailable"), refresh=False)
            return
        self.operation_started.emit("delete profile")

        def _do():
            return self.engine.delete(
                name, on_line=lambda line: self.operation_output.emit("delete profile", line),
            )

        def _on_done(res):
            self._after_op("delete profile", res)

        self.run(_do, _on_done, lambda e: self._after_op("delete profile", self._fail(str(e))))

    # ── container ops ─────────────────────────────────────────────────────

    def start_container(self, ref: str) -> None:
        if self.engine is None:
            self._after_op("start container", self._fail(self._engine_error or "engine unavailable"), refresh=False)
            return
        self.operation_started.emit("start container")
        self.run(
            lambda: self.engine.container_service.start(
                ref, on_line=lambda line: self.operation_output.emit("start container", line),
            ),
            lambda r: self._after_op("start container", r),
            lambda e: self._after_op("start container", self._fail(str(e))),
        )

    def stop_container(self, ref: str) -> None:
        if self.engine is None:
            self._after_op("stop container", self._fail(self._engine_error or "engine unavailable"), refresh=False)
            return
        self.operation_started.emit("stop container")
        self.run(
            lambda: self.engine.container_service.stop(
                ref, on_line=lambda line: self.operation_output.emit("stop container", line),
            ),
            lambda r: self._after_op("stop container", r),
            lambda e: self._after_op("stop container", self._fail(str(e))),
        )

    def remove_container(self, ref: str, force: bool = False) -> None:
        if self.engine is None:
            self._after_op("remove container", self._fail(self._engine_error or "engine unavailable"), refresh=False)
            return
        self.operation_started.emit("remove container")
        self.run(
            lambda: self.engine.container_service.remove(
                ref, force=force, on_line=lambda line: self.operation_output.emit("remove container", line),
            ),
            lambda r: self._after_op("remove container", r),
            lambda e: self._after_op("remove container", self._fail(str(e))),
        )

    def show_logs(self, ref: str, tail=1000) -> None:
        if self.engine is None:
            if self._logs_handler is not None:
                self._logs_handler(OperationResult(success=False, stderr=self._engine_error or "engine unavailable"))
            return

        def _do():
            return self.engine.container_service.logs(ref, tail)

        def _on_done(res):
            if self._logs_handler is not None:
                self._logs_handler(res)

        self.run(_do, _on_done, lambda e: self._logs_handler and self._logs_handler(
            OperationResult(success=False, stderr=str(e))
        ))

    def show_container_logs(self, container_name: str, tail=1000) -> None:
        from .gui.dialogs import ContainerLogsDialog
        dlg = ContainerLogsDialog(self, container_name, tail)
        dlg.exec()

    def compose_logs(self, config_file: str, service: Optional[str] = None, tail=1000) -> None:
        if self.engine is None:
            if self._logs_handler is not None:
                self._logs_handler(OperationResult(success=False, stderr=self._engine_error or "engine unavailable"))
            return
        def _do():
            return self.engine.container_service.compose_logs(config_file, service, tail)
        def _on_done(res):
            if self._logs_handler is not None:
                self._logs_handler(res)
        self.run(_do, _on_done, lambda e: self._logs_handler and self._logs_handler(
            OperationResult(success=False, stderr=str(e))
        ))

    # ── image ops ─────────────────────────────────────────────────────────

    def pull_image(self, image: str) -> None:
        if self.engine is None:
            self._after_op("pull image", self._fail(self._engine_error or "engine unavailable"), refresh=False)
            return
        self.operation_started.emit("pull image")
        self.run(
            lambda: self.engine.image_service.pull(
                image, on_line=lambda line: self.operation_output.emit("pull image", line),
            ),
            lambda r: self._after_op("pull image", r),
            lambda e: self._after_op("pull image", self._fail(str(e))),
        )

    def remove_image(self, image: str, force: bool = False) -> None:
        if self.engine is None:
            self._after_op("remove image", self._fail(self._engine_error or "engine unavailable"), refresh=False)
            return
        self.operation_started.emit("remove image")
        self.run(
            lambda: self.engine.image_service.remove(
                image, force=force, on_line=lambda line: self.operation_output.emit("remove image", line),
            ),
            lambda r: self._after_op("remove image", r),
            lambda e: self._after_op("remove image", self._fail(str(e))),
        )

    # ── compose stacks ────────────────────────────────────────────────────

    def compose_up(self, config_file: str) -> None:
        if self.engine is None:
            self._after_op("compose up", self._fail(self._engine_error or "engine unavailable"), refresh=False)
            return
        self.operation_started.emit("compose up")
        self.run(
            lambda: self.engine.container_service.compose_up(
                config_file, on_line=lambda line: self.operation_output.emit("compose up", line),
            ),
            lambda r: self._after_op("compose up", r),
            lambda e: self._after_op("compose up", self._fail(str(e))),
        )

    def compose_down(self, config_file: str) -> None:
        if self.engine is None:
            self._after_op("compose down", self._fail(self._engine_error or "engine unavailable"), refresh=False)
            return
        self.operation_started.emit("compose down")
        self.run(
            lambda: self.engine.container_service.compose_down(
                config_file, on_line=lambda line: self.operation_output.emit("compose down", line),
            ),
            lambda r: self._after_op("compose down", r),
            lambda e: self._after_op("compose down", self._fail(str(e))),
        )

    def compose_start(self, config_file: str) -> None:
        if self.engine is None:
            self._after_op("compose start", self._fail(self._engine_error or "engine unavailable"), refresh=False)
            return
        self.operation_started.emit("compose start")
        self.run(
            lambda: self.engine.container_service.compose_start(
                config_file, on_line=lambda line: self.operation_output.emit("compose start", line),
            ),
            lambda r: self._after_op("compose start", r),
            lambda e: self._after_op("compose start", self._fail(str(e))),
        )

    def compose_stop(self, config_file: str) -> None:
        if self.engine is None:
            self._after_op("compose stop", self._fail(self._engine_error or "engine unavailable"), refresh=False)
            return
        self.operation_started.emit("compose stop")
        self.run(
            lambda: self.engine.container_service.compose_stop(
                config_file, on_line=lambda line: self.operation_output.emit("compose stop", line),
            ),
            lambda r: self._after_op("compose stop", r),
            lambda e: self._after_op("compose stop", self._fail(str(e))),
        )

    def set_logs_handler(self, handler) -> None:
        self._logs_handler = handler

    def show_compose_logs(self, project) -> None:
        # Defer import to avoid circular import at module load.
        from .gui.dialogs import ComposeLogsDialog
        dlg = ComposeLogsDialog(self, project)
        dlg.exec()

    # ── config ────────────────────────────────────────────────────────────

    def save_config(self) -> None:
        ColimaConfigStore.save(self.config)

    def update_start_args(self, args: List[str]) -> None:
        self.config.start_args = list(args)
        self.save_config()

    # ── tray entry ────────────────────────────────────────────────────────

    def show_window(self) -> None:
        if self._window is not None:
            self._window.showNormal()
            self._window.raise_()
            self._window.activateWindow()

    def _teardown(self) -> None:
        """Clean up threads/timers so macOS doesn't report an unexpected exit."""
        if getattr(self, "_shutting_down", False):
            return
        self._shutting_down = True
        # Stop periodic timers.
        for attr in ("_state_timer", "_stats_timer"):
            t = getattr(self, attr, None)
            if t is not None:
                try:
                    t.stop()
                except Exception:
                    pass
        # Stop any active log streamers in open dialogs.
        try:
            from PySide6.QtWidgets import QApplication
            for w in QApplication.topLevelWidgets():
                stop = getattr(w, "_stop_stream", None)
                if callable(stop):
                    try:
                        stop()
                    except Exception:
                        pass
                # Close dialogs (they stop their own timers in closeEvent).
                if w is not self._window and w is not None:
                    try:
                        w.close()
                    except Exception:
                        pass
        except Exception:
            pass
        # Wait for worker threads to finish (with a timeout), then terminate
        # any stragglers so the interpreter doesn't crash during teardown.
        for w in list(self._workers):
            try:
                if w.isRunning():
                    w.wait(3000)
                    if w.isRunning():
                        w.terminate()
                        w.wait(1000)
            except Exception:
                pass
        self._workers.clear()

    def quit(self) -> None:
        self.log("\x1b[33mColima Desktop shutting down…\x1b[0m")
        self._teardown()
        if self._window is not None:
            self._window.close()
        if self._tray is not None:
            self._tray.hide()
        # Actually terminate the event loop (the window close only hides it).
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.quit()