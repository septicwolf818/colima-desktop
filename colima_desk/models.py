"""Domain models for Colima Desk.

These are plain dataclasses with no Qt dependency so the engine layer stays
GUI-agnostic and the code can be reused by other front-ends or by tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ColimaState:
    """Current state of the active (default or chosen) colima profile."""

    running: bool = False
    runtime: Optional[str] = None  # e.g. "docker", "containerd", "docker+k3s"
    profile: str = "default"
    version: Optional[str] = None
    error: Optional[str] = None


@dataclass
class Profile:
    """A colima profile (multi-instance). Maps to the user's "project" concept."""

    name: str = ""
    status: str = ""  # Running / Stopped / Error / ...
    arch: str = ""
    cpus: str = ""
    memory: str = ""
    disk: str = ""
    runtime: str = ""
    address: str = ""

    @property
    def running(self) -> bool:
        return self.status.lower() in ("running", "up")

    @property
    def runtime_family(self) -> str:
        """'docker' or 'containerd' (docker+k3s -> docker)."""
        return "containerd" if "containerd" in self.runtime.lower() else "docker"


@dataclass
class Container:
    """A single container as reported by docker/nerdctl."""

    id: str = ""
    name: str = ""
    image: str = ""
    command: str = ""
    state: str = ""  # running / exited / ...
    status: str = ""  # human readable, e.g. "Up About a minute"
    created_at: str = ""
    running_for: str = ""
    ports: str = ""
    size: str = ""
    networks: str = ""
    platform: dict = field(default_factory=dict)
    labels: dict = field(default_factory=dict)
    # Compose / project metadata (parsed from labels).
    project: str = ""           # com.docker.compose.project
    service: str = ""           # com.docker.compose.service
    config_files: str = ""      # com.docker.compose.project.config_files
    working_dir: str = ""       # com.docker.compose.project.working_dir

    @property
    def is_compose(self) -> bool:
        return bool(self.project)

    @property
    def is_running(self) -> bool:
        return self.state.lower() in ("running", "up")

    @property
    def short_id(self) -> str:
        return self.id[:12]


@dataclass
class ComposeProject:
    """A Docker Compose project (stack) grouped from container labels."""

    name: str = ""
    working_dir: str = ""
    config_files: str = ""
    containers: List["Container"] = field(default_factory=list)

    @property
    def running(self) -> bool:
        return any(c.is_running for c in self.containers)

    @property
    def status(self) -> str:
        if not self.containers:
            return "empty"
        if all(c.is_running for c in self.containers):
            return "running"
        if any(c.is_running for c in self.containers):
            return "partial"
        return "stopped"

    @property
    def container_count(self) -> int:
        return len(self.containers)


@dataclass
class ContainerStat:
    """Live usage for a single container (from docker stats)."""

    id: str = ""
    name: str = ""
    cpu: str = ""
    memory: str = ""
    memory_percent: str = ""
    net_io: str = ""
    pids: str = ""


@dataclass
class Image:
    """A single image as reported by docker/nerdctl."""

    id: str = ""
    repository: str = ""
    tag: str = ""
    size: str = ""
    created_since: str = ""
    created_at: str = ""
    digest: str = ""
    shared_size: str = ""
    unique_size: str = ""
    containers: int = 0


@dataclass
class OperationResult:
    """Result of running a colima / docker / nerdctl command."""

    success: bool = False
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0

    @property
    def message(self) -> str:
        return self.stderr.strip() or self.stdout.strip() or f"rc={self.returncode}"
