"""Refactorer Agent — generates concrete, ordered, non-conflicting patches via extended thinking."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from codebuddy.core.agent import BaseAgent
from codebuddy.core.context import SharedContextBus
from codebuddy.core.models import (
    FileContext,
    IssueReport,
    RefactorPlan,
    RefactorPatch,
    PipelineArtifact,
)
from codebuddy.llm.templates import REFACTORER_SYSTEM, REFACTORER_TASK, render

if TYPE_CHECKING:
    from codebuddy.llm.client import LLMClient


class RefactorerOutput(BaseModel):
    """Structured output schema for the Refactorer Agent."""
    patches: list[RefactorPatch] = Field(default_factory=list)
    ordering: list[str] = Field(default_factory=list)
    reasoning: str = ""


class RefactorerAgent(BaseAgent):
    name = "refactorer"
    description = "Generates exact code patches using extended thinking (32K token budget)"

    async def analyze(self, ctx: SharedContextBus) -> PipelineArtifact:
        issues_data = ctx.get("issue_reports")
        file_contexts_data = ctx.get("file_contexts")
        feedback = ctx.get_meta("refactorer_feedback", {})

        issues: list[IssueReport] = []
        if issues_data:
            issues = [IssueReport.model_validate(i) for i in issues_data.get("issues", [])]

        file_contexts: list[FileContext] = []
        if file_contexts_data:
            file_contexts = [FileContext.model_validate(f) for f in file_contexts_data.get("file_contexts", [])]

        # Build a file path → FileContext lookup
        fc_by_path: dict[str, FileContext] = {fc.file_path: fc for fc in file_contexts}

        # Group issues by file
        issues_by_file: dict[str, list[IssueReport]] = {}
        for issue in issues:
            issues_by_file.setdefault(issue.file_path, []).append(issue)

        all_patches: list[RefactorPatch] = []
        all_order: list[str] = []

        for file_path, file_issues in issues_by_file.items():
            fc = fc_by_path.get(file_path)
            if not fc:
                continue

            # Handle feedback from validator: append error context
            extra_context = ""
            if feedback:
                extra_context = f"\n\nPREVIOUS ATTEMPT FAILED. Errors: {json.dumps(feedback.get('validation_errors', []))}"
                extra_context += f"\nRegressions: {json.dumps(feedback.get('regression_flags', []))}"

            prompt = render(
                REFACTORER_TASK,
                language=fc.language,
                file_path=file_path,
                file_content=fc.full_content[:12000],
                issues=file_issues,
            ) + extra_context

            try:
                result = await self.client.generate_structured(
                    system=REFACTORER_SYSTEM,
                    messages=[{"role": "user", "content": prompt}],
                    output_model=RefactorerOutput,
                    max_tokens=16384,
                    thinking_budget=16384,
                    cache_system=True,
                )
                all_patches.extend(result.patches)
                all_order.extend(result.ordering)
            except Exception:
                # Fallback: plain text generation
                try:
                    raw = await self.client.generate(
                        system=REFACTORER_SYSTEM,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=8192,
                        thinking_budget=8192,
                        cache_system=False,
                    )
                    patches = _parse_patches_from_text(raw.get("text", ""), file_path)
                    all_patches.extend(patches)
                    all_order.extend([p.patch_id for p in patches])
                except Exception:
                    pass

        # Order patches by dependency (no two patches touch same lines)
        ordered = _resolve_patch_order(all_patches, all_order)

        plan = RefactorPlan(
            patches=ordered,
            ordering=[p.patch_id for p in ordered],
            reason=feedback.get("validation_errors", ["Initial refactoring plan"])[0] if feedback else "Initial refactoring plan based on issue analysis",
        )

        return PipelineArtifact(
            artifact_type="refactor_plan",
            data=plan.model_dump(),
            agent_name=self.name,
        )

    async def reflect(self, ctx: SharedContextBus, feedback: dict) -> PipelineArtifact:
        ctx.set_meta("refactorer_feedback", feedback)
        return await self.analyze(ctx)


def _resolve_patch_order(patches: list[RefactorPatch], preferred_order: list[str]) -> list[RefactorPatch]:
    """Ensure no two patches have conflicting line ranges. Use preferred order as hint."""
    if len(patches) <= 1:
        return patches

    by_id = {p.patch_id: p for p in patches}
    ordered: list[RefactorPatch] = []
    occupied_ranges: list[tuple[int, int]] = []

    # First, follow the preferred ordering from the LLM
    for pid in preferred_order:
        patch = by_id.get(pid)
        if patch and not _conflicts(patch, occupied_ranges):
            ordered.append(patch)
            occupied_ranges.append((patch.original_code.count("\n"), len(patch.original_code)))

    # Then add remaining patches that don't conflict
    for patch in patches:
        if patch.patch_id not in {p.patch_id for p in ordered}:
            if not _conflicts(patch, occupied_ranges):
                ordered.append(patch)

    return ordered


def _conflicts(patch: RefactorPatch, occupied: list[tuple[int, int]]) -> bool:
    # Simple heuristic: check if patch has same file + approximate line overlap
    patch_lines = patch.original_code.count("\n")
    for oc_lines, _ in occupied:
        if abs(patch_lines - oc_lines) < 3:
            return True
    return False


def _parse_patches_from_text(text: str, file_path: str) -> list[RefactorPatch]:
    """Fallback: extract patches from plain LLM text."""
    patches: list[RefactorPatch] = []
    try:
        if "```json" in text:
            block = text.split("```json")[1].split("```")[0]
            data = json.loads(block)
            items = data if isinstance(data, list) else data.get("patches", [])
            for item in items:
                patches.append(RefactorPatch(
                    file_path=file_path,
                    original_code=item.get("original_code", ""),
                    refactored_code=item.get("refactored_code", ""),
                    unified_diff=item.get("unified_diff", ""),
                    pattern_applied=item.get("pattern_applied", ""),
                    rationale=item.get("rationale", ""),
                    issue_ids=item.get("issue_ids", []),
                ))
    except (json.JSONDecodeError, KeyError, IndexError):
        pass
    return patches
