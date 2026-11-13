"""Image service: lists images, pull, and remove.

Dispatches to ``docker images`` / ``docker pull`` / ``docker rmi`` for docker
runtimes and ``nerdctl`` equivalents for containerd runtimes.
"""

from __future__ import annotations

import json
from typing import Callable, List, Optional

from .colima_engine import ColimaEngine
from ..models import Image, OperationResult


def _json_lines(output: str) -> List[dict]:
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


class ImageService:
    """All image operations, normalized across runtimes."""

    def __init__(self, engine: ColimaEngine) -> None:
        self._engine = engine

    def _cli_for(self) -> Optional[str]:
        if self._engine._runtime_family() == "containerd":
            return self._engine.nerdctl_cli()
        return self._engine.docker_cli()

    # ── listing ───────────────────────────────────────────────────────────

    def list(self, on_line: Optional[Callable[[str], None]] = None) -> List[Image]:
        cli = self._cli_for()
        if cli is None:
            return []
        cmd = [cli, "images", "--format", "{{json .}}"]
        stdout, _, _ = self._engine._run(cmd, 60, on_line=on_line)
        return [self._raw_to_image(r) for r in _json_lines(stdout)]

    @staticmethod
    def _raw_to_image(raw: dict) -> Image:
        containers_raw = raw.get("Containers", "0")
        try:
            containers = int(containers_raw)
        except (TypeError, ValueError):
            containers = 0
        return Image(
            id=raw.get("ID") or "",
            repository=raw.get("Repository") or "",
            tag=raw.get("Tag") or "",
            size=raw.get("Size") or "",
            created_since=raw.get("CreatedSince") or "",
            created_at=raw.get("CreatedAt") or "",
            digest=raw.get("Digest") or "",
            shared_size=raw.get("SharedSize") or "",
            unique_size=raw.get("UniqueSize") or "",
            containers=containers,
        )

    # ── operations ────────────────────────────────────────────────────────

    def pull(self, image: str, on_line: Optional[Callable[[str], None]] = None) -> OperationResult:
        cli = self._cli_for()
        if cli is None:
            return self._engine._fail("no container runtime available")
        cmd = [cli, "pull", image]
        sock = None
        if self._engine is not None:
            sock = self._engine.docker_socket()
        env = {"DOCKER_HOST": sock} if sock else None
        return self._engine._run_cmd(cmd, timeout=600, on_line=on_line, env=env)

    def remove(self, image: str, force: bool = False, on_line: Optional[Callable[[str], None]] = None) -> OperationResult:
        cli = self._cli_for()
        if cli is None:
            return self._engine._fail("no container runtime available")
        cmd = [cli, "rmi"]
        if force:
            cmd.append("-f")
        cmd.append(image)
        sock = None
        if self._engine is not None:
            sock = self._engine.docker_socket()
        env = {"DOCKER_HOST": sock} if sock else None
        return self._engine._run_cmd(cmd, timeout=120, on_line=on_line, env=env)

    def tags(self, image: str) -> List[str]:
        """List tags for an image (useful for the pull dialog)."""
        cli = self._cli_for()
        if cli is None:
            return []
        cmd = [cli, "images", "--format", "{{.Repository}}:{{.Tag}}"]
        out = self._engine._run(cmd, 30)[0]
        tags = [t for t in (line.strip() for line in out.splitlines() if line.strip())]
        return [t for t in tags if t.lower().startswith(image.lower())]