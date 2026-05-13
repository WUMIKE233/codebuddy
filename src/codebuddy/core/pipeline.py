"""PipelineOrchestrator — coordinates Scanner → Analyzer → Refactorer → Validator."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog

from codebuddy.core.context import SharedContextBus
from codebuddy.core.models import (
    FileContext,
    IssueReport,
    PipelineResult,
    PipelineStatus,
    RefactorPlan,
    ValidationReport,
)

if TYPE_CHECKING:
    from codebuddy.config import Config
    from codebuddy.llm.client import LLMClient
    from codebuddy.core.agent import BaseAgent

logger = structlog.get_logger(__name__)


class PipelineOrchestrator:
    """Orchestrates the four-agent pipeline with loop-back on validation failure.

    Flow:
        Scanner → Analyzer → Refactorer → Validator
                      ↑________________________|
                      (up to max_iterations times)

    Each agent reads upstream artifacts from the SharedContextBus and
    writes its output back. The Orchestrator owns the bus and the
    sequencing logic.
    """

    def __init__(
        self,
        config: Config,
        client: LLMClient,
        agents: dict[str, BaseAgent],
    ) -> None:
        self.config = config
        self.client = client
        self.agents = agents
        self.ctx = SharedContextBus()

    # ── Public API ──────────────────────────────────────────────────────────

    async def run(
        self,
        diff_content: str = "",
        file_list: list[str] | None = None,
    ) -> PipelineResult:
        """Run the full pipeline and return an aggregate result."""
        started_at = datetime.now(tz=timezone.utc).isoformat()

        self.ctx.set_meta("diff_content", diff_content)
        self.ctx.set_meta("file_list", file_list or [])

        try:
            # Phase 1: Scanner (file discovery + classification)
            logger.info("pipeline.scanner.start")
            scanner_artifact = await self.agents["scanner"].analyze(self.ctx)
            self.ctx.put("file_contexts", scanner_artifact.data, agent_name="scanner")
            logger.info(
                "pipeline.scanner.done",
                file_count=len(scanner_artifact.data.get("file_contexts", [])),
            )

            # Phase 2: Analyzer (find issues with root-cause chains)
            logger.info("pipeline.analyzer.start")
            analyzer_artifact = await self.agents["analyzer"].analyze(self.ctx)
            self.ctx.put("issue_reports", analyzer_artifact.data, agent_name="analyzer")
            issues = analyzer_artifact.data.get("issues", [])
            logger.info("pipeline.analyzer.done", issue_count=len(issues))

            # Phase 3 + 4: Refactorer + Validator with loop-back
            refactor_plan = await self._refactor_validate_loop()
        except Exception as exc:
            logger.exception("pipeline.error", error=str(exc))
            return PipelineResult(
                status=PipelineStatus.FAIL,
                started_at=started_at,
                finished_at=datetime.now(tz=timezone.utc).isoformat(),
                total_tokens=self.client.total_tokens,
                error=str(exc),
            )

        # Collect results
        file_ctx_data = self.ctx.get("file_contexts") or {}
        issue_data = self.ctx.get("issue_reports") or {}
        validation_data = self.ctx.get("validation_report") or {}

        return PipelineResult(
            status=PipelineStatus(validation_data.get("overall_status", "fail")),
            file_contexts=[FileContext.model_validate(f) for f in file_ctx_data.get("file_contexts", [])],
            issues=[IssueReport.model_validate(i) for i in issue_data.get("issues", [])],
            refactor_plan=refactor_plan,
            validation=ValidationReport.model_validate(validation_data) if validation_data else None,
            iterations=self.ctx.get_meta("iterations", 1),
            started_at=started_at,
            finished_at=datetime.now(tz=timezone.utc).isoformat(),
            total_tokens=self.client.total_tokens,
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _refactor_validate_loop(self) -> RefactorPlan | None:
        """Run refactorer → validator, looping on validation failure."""
        max_iters = self.config.pipeline.max_iterations

        for iteration in range(1, max_iters + 1):
            self.ctx.set_meta("iterations", iteration)

            # Refactor
            logger.info("pipeline.refactorer.start", iteration=iteration)
            refactor_artifact = await self.agents["refactorer"].analyze(self.ctx)
            self.ctx.put(
                "refactor_plan", refactor_artifact.data, agent_name="refactorer"
            )
            plan_data = refactor_artifact.data
            plan = RefactorPlan.model_validate(plan_data)
            logger.info("pipeline.refactorer.done", patch_count=len(plan.patches))

            # Validate
            logger.info("pipeline.validator.start", iteration=iteration)
            validate_artifact = await self.agents["validator"].analyze(self.ctx)
            self.ctx.put(
                "validation_report", validate_artifact.data, agent_name="validator"
            )
            report = ValidationReport.model_validate(validate_artifact.data)
            logger.info(
                "pipeline.validator.done",
                status=report.overall_status.value,
                iteration=iteration,
            )

            if report.overall_status == PipelineStatus.PASS:
                return plan

            if report.overall_status == PipelineStatus.FAIL and iteration < max_iters:
                # Provide feedback to refactorer for another attempt
                feedback = {
                    "validation_errors": report.errors,
                    "regression_flags": report.regression_flags,
                    "failed_tests": report.test_results.failed,
                }
                logger.info("pipeline.loopback", iteration=iteration, feedback=feedback)
                self.ctx.set_meta("refactorer_feedback", feedback)
                await asyncio.sleep(0.1)  # Brief yield between loop iterations
            else:
                return plan

        return plan
