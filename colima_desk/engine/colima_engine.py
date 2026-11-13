"""Core Colima engine: lifecycle (start/stop/restart/delete), profiles, state,
and a shared subprocess runner used by the container/image services.

This module is pure-Python and GUI-agnostic.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from typing import Callable, List, Optional, Sequence, Tuple

from ..models import ColimaState, Profile, OperationResult

# Default locations for the colima binary.
_DEFAULT_CLI_CANDIDATES = (
    "colima",
    "/opt/homebrew/bin/colima",
    "/usr/local/bin/colima",
    os.path.join(os.path.expanduser("~"), ".local/bin", "colima"),
)


class EngineError(RuntimeError):
    """Raised when the engine cannot operate (e.g. no CLI found)."""


class ColimaEngine:
    """Facade over the colima CLI plus the container/image services.

    The engine resolves the colima binary at construction time and keeps
    lazy container/image services that read the current runtime from the
    engine so they dispatch to ``docker`` vs ``nerdctl`` correctly.
    """

    def __init__(self, cli_path: Optional[str] = None) -> None:
        self._cli_path: Optional[str] = cli_path or self._find_cli()
        if self._cli_path is None:
            raise EngineError("colima binary not found; install colima or add it to PATH")
        # Lazy services so we don't require the docker/nerdctl CLIs at import time.
        from .container_service import ContainerService
        from .image_service import ImageService

        self._container_service = ContainerService(self)
        self._image_service = ImageService(self)

    # ── public state / list accessors ─────────────────────────────────────

    @property
    def container_service(self):
        return self._container_service

    @property
    def image_service(self):
        return self._image_service

    @property
    def cli_path(self) -> Optional[str]:
        return self._cli_path

    def get_state(self, on_line: Optional[Callable[[str], None]] = None) -> ColimaState:
        """Return the running/stopped state + runtime of the active profile."""
        profile = getattr(self, "_state_profile", "default")
        stdout, stderr, rc = self._run([self._cli_path, "status"], on_line=on_line)
        blob = f"{stdout}\n{stderr}".lower()
        if "colima is running" in blob or " is running" in blob:
            running = True
        elif "colima is not running" in blob or "is not running" in blob:
            running = False
        else:
            # Fallback: a clean exit implies running.
            running = rc == 0
        runtime = None
        m = re.search(
            r"\bruntime:\s*([a-zA-Z0-9_+/-]+)",
            f"{stdout}\n{stderr}",
            re.IGNORECASE,
        )
        if m:
            runtime = m.group(1).strip()
        error = None
        if not running:
            if "colima is not running" in blob:
                error = "Colima is not running (start it to manage containers/images)"
        return ColimaState(running=running, runtime=runtime, profile=profile, error=error)

    def list_profiles(self, on_line: Optional[Callable[[str], None]] = None) -> List[Profile]:
        """Parse `colima list -v` into a list of :class:`Profile`."""
        stdout, stderr, rc = self._run([self._cli_path, "list", "-v"], timeout=30, on_line=on_line)
        if not stdout or rc != 0 and not stdout:
            return []
        rows: List[List[str]] = []
        for line in stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split()
            if not parts or parts[0].upper() == "PROFILE":
                continue
            rows.append(parts)
        return [self._row_to_profile(r) for r in rows]

    def get_profile(self, name: Optional[str] = None) -> Optional[Profile]:
        """Find a specific profile by name (case-insensitive)."""
        name = (name or "").lower()
        if not name:
            return None
        for p in self.list_profiles():
            if p.name.lower() == name:
                return p
        return None

    # ── lifecycle operations ──────────────────────────────────────────────

    def start(self, profile: Optional[str] = None, args: Sequence[str] = (), on_line: Optional[Callable[[str], None]] = None) -> OperationResult:
        cmd = [self._cli_path, "start"]
        if profile:
            cmd += ["--profile", profile]
        cmd += [a for a in args if a]
        return self._run_cmd(cmd, on_line=on_line)

    def stop(self, profile: Optional[str] = None, on_line: Optional[Callable[[str], None]] = None) -> OperationResult:
        cmd = [self._cli_path, "stop"]
        if profile:
            cmd += ["--profile", profile]
        return self._run_cmd(cmd, timeout=120, on_line=on_line)

    def restart(self, profile: Optional[str] = None, on_line: Optional[Callable[[str], None]] = None) -> OperationResult:
        cmd = [self._cli_path, "restart"]
        if profile:
            cmd += ["--profile", profile]
        return self._run_cmd(cmd, timeout=120, on_line=on_line)

    def delete(self, profile: Optional[str] = None, on_line: Optional[Callable[[str], None]] = None) -> OperationResult:
        if not profile:
            return self._fail("a profile name is required to delete")
        cmd = [self._cli_path, "delete", profile]
        return self._run_cmd(cmd, timeout=180, on_line=on_line)

    def version(self) -> str:
        stdout, stderr, rc = self._run([self._cli_path, "version"], timeout=15)
        if rc == 0 and stdout:
            return stdout.splitlines()[0]
        return "unknown"

    # ── profile configuration (colima.yaml) ───────────────────────────────

    def profile_config_path(self, profile: Optional[str] = None) -> str:
        name = profile or "default"
        return os.path.join(os.path.expanduser("~"), ".colima", name, "colima.yaml")

    def read_profile_config(self, profile: Optional[str] = None) -> dict:
        """Read editable fields from a profile's colima.yaml."""
        path = self.profile_config_path(profile)
        result = {}
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or ":" not in line:
                        continue
                    key, _, val = line.partition(":")
                    key = key.strip()
                    val = val.strip()
                    if key in ("cpu", "memory", "disk", "runtime", "arch", "kubernetes"):
                        result[key] = val
        except (FileNotFoundError, OSError):
            pass
        return result

    def write_profile_config(self, profile: Optional[str], values: dict) -> OperationResult:
        """Update editable fields in a profile's colima.yaml (targeted replace)."""
        import re as _re
        path = self.profile_config_path(profile)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except (FileNotFoundError, OSError) as exc:
            return OperationResult(success=False, stderr=str(exc), returncode=1)
        for key, val in values.items():
            if key == "kubernetes":
                # kubernetes is a nested block; update the `enabled` sub-key.
                pattern = _re.compile(r"^(\s*enabled:\s*).*$", _re.MULTILINE)
                if pattern.search(text):
                    text = pattern.sub(rf"\g<1>{val}", text)
                else:
                    # Insert under the kubernetes: block.
                    text = text.replace("kubernetes:\n", f"kubernetes:\n  enabled: {val}\n", 1)
            else:
                pattern = _re.compile(rf"^{_re.escape(key)}:\s*.*$", _re.MULTILINE)
                if pattern.search(text):
                    text = pattern.sub(f"{key}: {val}", text)
                else:
                    text = text.rstrip() + f"\n{key}: {val}\n"
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            return OperationResult(success=False, stderr=str(exc), returncode=1)
        return OperationResult(success=True, stdout="saved", returncode=0)

    # ── internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _find_cli() -> Optional[str]:
        executable = shutil.which("colima")
        if executable:
            return executable
        for candidate in _DEFAULT_CLI_CANDIDATES[1:]:
            if candidate == "colima":
                continue
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        return None

    def _row_to_profile(self, parts: List[str]) -> Profile:
        # Expected columns: PROFILE STATUS ARCH CPUS MEMORY DISK RUNTIME [ADDRESS]
        def _val(idx, default=""):
            return parts[idx] if idx < len(parts) else default

        runtime = _val(6)
        # If runtime token is empty, the address may have shifted. Handle both.
        address = _val(7)
        return Profile(
            name=_val(0),
            status=_val(1),
            arch=_val(2),
            cpus=_val(3),
            memory=_val(4),
            disk=_val(5),
            runtime=runtime,
            address=address,
        )

    def _run(
        self,
        cmd: Sequence[str],
        timeout: int = 60,
        on_line: Optional[Callable[[str], None]] = None,
        env: Optional[dict] = None,
    ) -> Tuple[str, str, int]:
        run_env = None
        if env:
            run_env = dict(os.environ)
            run_env.update(env)
        if on_line is None:
            # Non-streaming: capture everything, return at the end.
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=run_env,
                )
                return (
                    result.stdout.strip(),
                    result.stderr.strip(),
                    result.returncode,
                )
            except subprocess.TimeoutExpired:
                return "", f"command timed out after {timeout}s", 253
            except FileNotFoundError:
                return "", f"command not found: {cmd[0]}", 127
            except OSError as exc:
                return "", str(exc), 128
        # Streaming: emit each line as it arrives; capture stderr separately.
        import subprocess as _sp
        import threading
        collected: List[str] = []
        stderr_collected: List[str] = []
        try:
            proc = _sp.Popen(
                list(cmd),
                stdout=_sp.PIPE,
                stderr=_sp.PIPE,
                text=True,
                bufsize=1,
                env=run_env,
            )
            assert proc.stdout is not None
            assert proc.stderr is not None

            def _read_stderr() -> None:
                try:
                    for raw in proc.stderr:
                        stderr_collected.append(raw)
                        try:
                            on_line(raw)
                        except Exception:
                            pass
                except Exception:
                    pass

            stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
            stderr_thread.start()

            for raw in proc.stdout:
                collected.append(raw)
                try:
                    on_line(raw)
                except Exception:
                    pass
            stderr_thread.join()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    stderr_thread.join(timeout=5)
                except Exception:
                    pass
                collected.append(f"\ncommand timed out after {timeout}s\n")
                return "".join(collected).strip(), "".join(stderr_collected).strip(), 253
            return "".join(collected).strip(), "".join(stderr_collected).strip(), proc.returncode or 0
        except FileNotFoundError:
            msg = f"command not found: {cmd[0]}"
            try:
                on_line(msg + "\n")
            except Exception:
                pass
            return "", msg, 127
        except OSError as exc:
            msg = str(exc)
            try:
                on_line(msg + "\n")
            except Exception:
                pass
            return "", msg, 128

    def _run_cmd(
        self,
        cmd: Sequence[str],
        timeout: int = 60,
        on_line: Optional[Callable[[str], None]] = None,
        env: Optional[dict] = None,
    ) -> OperationResult:
        stdout, stderr, rc = self._run(cmd, timeout=timeout, on_line=on_line, env=env)
        return OperationResult(
            success=(rc == 0),
            stdout=stdout,
            stderr=stderr,
            returncode=rc,
        )

    def _fail(self, msg: str) -> OperationResult:
        return OperationResult(success=False, stderr=msg, returncode=1)

    def docker_cli(self) -> Optional[str]:
        """Path to the docker CLI, or None if runtime is containerd-based."""
        if self._runtime_family() != "docker":
            return None
        return shutil.which("docker") or (
            "/opt/homebrew/bin/docker"
            if os.path.exists("/opt/homebrew/bin/docker")
            else None
        )

    def docker_socket(self) -> Optional[str]:
        """Path to the colima docker socket for the active profile."""
        # Respect an explicit DOCKER_HOST if set.
        env_sock = os.environ.get("DOCKER_HOST", "")
        if env_sock.startswith("unix://"):
            return env_sock
        profile = getattr(self, "_state_profile", "default") or "default"
        # Map profile name to socket dir (default profile uses 'default').
        sock = os.path.join(
            os.path.expanduser("~"), ".colima", profile, "docker.sock",
        )
        if os.path.exists(sock):
            return "unix://" + sock
        # Fallback to default profile socket.
        sock = os.path.join(os.path.expanduser("~"), ".colima", "default", "docker.sock")
        if os.path.exists(sock):
            return "unix://" + sock
        return None

    def nerdctl_cli(self) -> Optional[str]:
        if self._runtime_family() != "containerd":
            return None
        return shutil.which("nerdctl") or (
            "/opt/homebrew/bin/nerdctl"
            if os.path.exists("/opt/homebrew/bin/nerdctl")
            else None
        )

    def _runtime_family(self) -> str:
        runtime = (self.get_state().runtime or "").lower()
        return "containerd" if "containerd" in runtime else "docker"