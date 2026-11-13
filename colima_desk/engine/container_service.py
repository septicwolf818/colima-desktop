"""Container service: lists containers, start/stop/remove, logs, and live stats.

Dispatches to the ``docker`` CLI for docker-based runtimes and ``nerdctl``
for containerd-based runtimes. Both are normalized into :class:`Container`
and :class:`ContainerStat` dataclasses.
"""

from __future__ import annotations

import json
from typing import Callable, List, Optional

from .colima_engine import ColimaEngine
from ..models import Container, ContainerStat, OperationResult


def _json_lines(output: str) -> List[dict]:
    """Yield each non-empty line of JSON as a dict."""
    items: List[dict] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items


def _parse_platform(raw: Optional[dict]) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    return {}


class ContainerService:
    """All container operations, normalized across runtimes."""

    def __init__(self, engine: ColimaEngine) -> None:
        self._engine = engine

    # ── listing ───────────────────────────────────────────────────────────

    def _docker_env(self) -> Optional[dict]:
        sock = self._engine.docker_socket()
        if sock:
            return {"DOCKER_HOST": sock}
        return None

    def list(self, all_: bool = True, on_line: Optional[Callable[[str], None]] = None) -> List[Container]:
        """List containers (running and optionally stopped)."""
        cli = self._cli_for("docker")
        if cli is None:
            return []
        cmd = [cli, "ps"]
        if all_:
            cmd.append("-a")
        cmd += ["--format", "{{json .}}"]
        return self._parse_ps(cmd, on_line=on_line, env=self._docker_env())

    def _cli_for(self, kind: str) -> Optional[str]:
        return self._engine.docker_cli() if kind == "docker" else self._engine.nerdctl_cli()

    def _parse_ps(self, cmd: List[str], on_line: Optional[Callable[[str], None]] = None, env: Optional[dict] = None) -> List[Container]:
        stdout, stderr, rc = self._engine._run(cmd, timeout=60, on_line=on_line, env=env)
        if rc != 0 and not stdout:
            return []
        out: List[Container] = []
        for raw in _json_lines(stdout):
            out.append(self._raw_to_container(raw))
        return out

    @staticmethod
    def _parse_labels(raw_labels) -> dict:
        """Parse docker's comma-separated 'k=v,k2=v2' label string into a dict."""
        out: dict = {}
        if isinstance(raw_labels, dict):
            return dict(raw_labels)
        if not isinstance(raw_labels, str) or not raw_labels.strip():
            return out
        for chunk in raw_labels.split(","):
            chunk = chunk.strip()
            if not chunk or "=" not in chunk:
                continue
            key, _, val = chunk.partition("=")
            out[key.strip()] = val.strip()
        return out

    @staticmethod
    def _raw_to_container(raw: dict) -> Container:
        """Normalize a docker/nerdctl ``ps --format json`` object."""
        names = raw.get("Names") or raw.get("Name") or raw.get("names") or raw.get("name") or ""
        if isinstance(names, str):
            names = [n.strip() for n in names.split(",") if n.strip()]
        elif isinstance(names, list):
            names = [str(n) for n in names]
        else:
            names = []

        created = raw.get("CreatedAt") or raw.get("Created") or ""
        state = raw.get("State") or raw.get("state") or ""
        status = raw.get("Status") or raw.get("status") or state
        labels = ContainerService._parse_labels(raw.get("Labels") or raw.get("labels"))

        project = labels.get("com.docker.compose.project", "")
        service = labels.get("com.docker.compose.service", "")
        config_files = labels.get("com.docker.compose.project.config_files", "")
        working_dir = labels.get("com.docker.compose.project.working_dir", "")

        return Container(
            id=raw.get("ID") or raw.get("Id") or "",
            name=names[0] if names else (raw.get("Name") or raw.get("name") or ""),
            image=raw.get("Image") or raw.get("image") or "",
            command=raw.get("Command") or raw.get("command") or "",
            state=state,
            status=status,
            created_at=created,
            running_for=raw.get("RunningFor") or raw.get("RunningFor") or "",
            ports=raw.get("Ports") or raw.get("ports") or "",
            size=raw.get("Size") or raw.get("size") or "",
            networks=raw.get("Networks") or raw.get("networks") or "",
            platform=_parse_platform(raw.get("Platform") or raw.get("platform")),
            labels=labels,
            project=project,
            service=service,
            config_files=config_files,
            working_dir=working_dir,
        )

    def list_compose_projects(self, on_line: Optional[Callable[[str], None]] = None) -> List:
        """Group compose containers into ComposeProject stacks."""
        from ..models import ComposeProject

        containers = self.list(on_line=on_line)
        projects: dict = {}
        for c in containers:
            if not c.is_compose:
                continue
            key = c.project
            if key not in projects:
                projects[key] = ComposeProject(
                    name=key,
                    working_dir=c.working_dir,
                    config_files=c.config_files,
                )
            projects[key].containers.append(c)
        # Sort containers within each project by service name.
        for p in projects.values():
            p.containers.sort(key=lambda c: c.service or c.name)
        return sorted(projects.values(), key=lambda p: p.name)

    # ── live stats ────────────────────────────────────────────────────────

    def stats(self, on_line: Optional[Callable[[str], None]] = None) -> List[ContainerStat]:
        """Non-streaming CPU/memory per running container."""
        cli = self._cli_for("docker")
        if cli is None:
            return []
        cmd = [cli, "stats", "--no-stream", "--format", "{{json .}}"]
        return self._parse_stats(cmd, on_line=on_line, env=self._docker_env())

    def _parse_stats(self, cmd: List[str], on_line: Optional[Callable[[str], None]] = None, env: Optional[dict] = None) -> List[ContainerStat]:
        stdout, stderr, rc = self._engine._run(cmd, timeout=15, on_line=on_line, env=env)
        if rc != 0 and not stdout:
            return []
        out: List[ContainerStat] = []
        for raw in _json_lines(stdout):
            out.append(self._raw_to_stat(raw))
        return out

    @staticmethod
    def _raw_to_stat(raw: dict) -> ContainerStat:
        return ContainerStat(
            id=raw.get("ID") or raw.get("Container") or "",
            name=raw.get("Name") or raw.get("Container") or "",
            cpu=raw.get("CPUPerc") or raw.get("CpuPerc") or raw.get("CPUCmd") or "",
            memory=raw.get("MemUsage") or raw.get("MemPerc") or "",
            memory_percent=raw.get("MemPerc") or raw.get("MemPerc") or "",
            net_io=raw.get("NetIO") or raw.get("NetIO") or "",
            pids=raw.get("PIDs") or raw.get("PIDs") or "",
        )

    def _match_stat(self, stat_id: str) -> bool:
        # used for joining stats to containers by short id
        return bool(stat_id)

    # ── operations ────────────────────────────────────────────────────────

    def start(self, ref: str, args: Optional[List[str]] = None, on_line: Optional[Callable[[str], None]] = None) -> OperationResult:
        cli = self._cli_for("docker")
        if cli is None:
            return self._fail("no docker runtime available")
        cmd = [cli, "start"] + ([a for a in (args or []) if a]) + [ref]
        return self._run_cmd(cmd, on_line=on_line, env=self._docker_env())

    def stop(self, ref: str, wait: bool = True, on_line: Optional[Callable[[str], None]] = None) -> OperationResult:
        cli = self._cli_for("docker")
        if cli is None:
            return self._fail("no docker runtime available")
        cmd = [cli, "stop", ref]
        if wait:
            cmd += ["--timeout", "10"]
        return self._run_cmd(cmd, timeout=120, on_line=on_line, env=self._docker_env())

    def remove(self, ref: str, force: bool = False, on_line: Optional[Callable[[str], None]] = None) -> OperationResult:
        cli = self._cli_for("docker")
        if cli is None:
            return self._fail("no docker runtime available")
        cmd = [cli, "rm"]
        if force:
            cmd.append("-f")
        cmd.append(ref)
        return self._run_cmd(cmd, on_line=on_line, env=self._docker_env())

    def logs(self, ref: str, tail=1000, on_line: Optional[Callable[[str], None]] = None) -> OperationResult:
        """Return the tail (or all) of a container's logs as stdout."""
        cli = self._cli_for("docker")
        if cli is None:
            return self._fail("no docker runtime available")
        cmd = [cli, "logs", "--timestamps", "--tail", str(tail), ref]
        return self._run_cmd(cmd, timeout=120, on_line=on_line, env=self._docker_env())

    # ── low-level ─────────────────────────────────────────────────────────

    def _cli(self) -> Optional[str]:
        return self._cli_for("docker")

    def cli(self, kind: str = "docker") -> Optional[str]:
        """Public accessor for the underlying container CLI path."""
        return self._cli_for(kind)

    # ── compose stacks ────────────────────────────────────────────────────

    def compose_up(self, config_file: str, on_line: Optional[Callable[[str], None]] = None) -> OperationResult:
        cli = self._cli_for("docker")
        if cli is None or not config_file:
            return self._engine._fail("no docker runtime or compose file")
        cmd = [cli, "compose", "-f", config_file, "up", "-d"]
        return self._engine._run_cmd(cmd, timeout=300, on_line=on_line, env=self._docker_env())

    def compose_down(self, config_file: str, on_line: Optional[Callable[[str], None]] = None) -> OperationResult:
        cli = self._cli_for("docker")
        if cli is None or not config_file:
            return self._engine._fail("no docker runtime or compose file")
        cmd = [cli, "compose", "-f", config_file, "down"]
        return self._engine._run_cmd(cmd, timeout=300, on_line=on_line, env=self._docker_env())

    def compose_start(self, config_file: str, on_line: Optional[Callable[[str], None]] = None) -> OperationResult:
        cli = self._cli_for("docker")
        if cli is None or not config_file:
            return self._engine._fail("no docker runtime or compose file")
        cmd = [cli, "compose", "-f", config_file, "start"]
        return self._engine._run_cmd(cmd, timeout=120, on_line=on_line, env=self._docker_env())

    def compose_stop(self, config_file: str, on_line: Optional[Callable[[str], None]] = None) -> OperationResult:
        cli = self._cli_for("docker")
        if cli is None or not config_file:
            return self._engine._fail("no docker runtime or compose file")
        cmd = [cli, "compose", "-f", config_file, "stop"]
        return self._engine._run_cmd(cmd, timeout=120, on_line=on_line, env=self._docker_env())

    def compose_logs(self, config_file: str, service: Optional[str] = None, tail=1000, on_line: Optional[Callable[[str], None]] = None) -> OperationResult:
        cli = self._cli_for("docker")
        if cli is None or not config_file:
            return self._engine._fail("no docker runtime or compose file")
        cmd = [cli, "compose", "-f", config_file, "logs", "--timestamps", "--tail", str(tail)]
        if service:
            cmd.append(service)
        return self._engine._run_cmd(cmd, timeout=120, on_line=on_line, env=self._docker_env())

    def _run_cmd(self, cmd: List[str], timeout: int = 60, on_line: Optional[Callable[[str], None]] = None, env: Optional[dict] = None) -> OperationResult:
        if env is None:
            env = self._docker_env()
        return self._engine._run_cmd(cmd, timeout=timeout, on_line=on_line, env=env)

    def _fail(self, msg: str) -> OperationResult:
        return self._engine._fail(msg)