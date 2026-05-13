"""Abstract base class for all CodeBuddy agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codebuddy.core.context import SharedContextBus
    from codebuddy.core.models import PipelineArtifact
    from codebuddy.llm.client import LLMClient


class BaseAgent(ABC):
    """Every agent in the pipeline inherits from this class.

    Agents are polymorphic: the PipelineOrchestrator calls `analyze()` and
    `reflect()` without knowing the concrete agent type.
    """

    name: str
    description: str = ""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @abstractmethod
    async def analyze(self, ctx: SharedContextBus) -> PipelineArtifact:
        """Core reasoning step. Reads upstream artifacts, produces downstream output."""
        ...

    async def reflect(
        self, ctx: SharedContextBus, feedback: dict
    ) -> PipelineArtifact:
        """Re-evaluate based on downstream feedback (used for loop-back).

        Default is to re-run analyze. Override for smarter reflection.
        """
        return await self.analyze(ctx)
