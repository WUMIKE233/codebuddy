"""SharedContextBus — typed, immutable artifact store passed between agents."""

from __future__ import annotations

import copy
from typing import Any
from collections import defaultdict

from codebuddy.core.models import PipelineArtifact


class SharedContextBus:
    """A typed key-value store that carries all pipeline artifacts.

    Each agent reads its upstream inputs (e.g., Scanner's FileContext list)
    and writes its output (e.g., Analyzer's IssueReport list). The bus is
    append-only for auditability — every write is recorded in the log.
    """

    def __init__(self) -> None:
        self._store: dict[str, PipelineArtifact] = {}
        self._log: list[PipelineArtifact] = []
        self._meta: dict[str, Any] = {}

    # ── Read / Write ─────────────────────────────────────────────────────────

    def put(self, artifact_type: str, data: dict, agent_name: str = "") -> PipelineArtifact:
        """Store an artifact. Returns the stored wrapper."""
        artifact = PipelineArtifact(
            artifact_type=artifact_type,
            data=data,
            agent_name=agent_name,
        )
        self._store[artifact_type] = artifact
        self._log.append(artifact)
        return artifact

    def get(self, artifact_type: str) -> dict | None:
        """Read the latest artifact of the given type (deep copy for safety)."""
        artifact = self._store.get(artifact_type)
        return copy.deepcopy(artifact.data) if artifact else None

    def get_artifact(self, artifact_type: str) -> PipelineArtifact | None:
        """Read the full wrapped artifact."""
        return self._store.get(artifact_type)

    # ── Metadata ─────────────────────────────────────────────────────────────

    def set_meta(self, key: str, value: Any) -> None:
        self._meta[key] = value

    def get_meta(self, key: str, default: Any = None) -> Any:
        return self._meta.get(key, default)

    # ── Audit ────────────────────────────────────────────────────────────────

    @property
    def log(self) -> list[PipelineArtifact]:
        return list(self._log)

    @property
    def artifact_types(self) -> list[str]:
        return list(self._store.keys())
