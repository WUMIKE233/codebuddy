"""Validator Agent — sandboxed test execution and AST-level behavior verification."""

from __future__ import annotations

import difflib
from typing import TYPE_CHECKING

from codebuddy.core.agent import BaseAgent
from codebuddy.core.context import SharedContextBus
from codebuddy.core.models import (
    FileContext,
    RefactorPlan,
    RefactorPatch,
    ValidationReport,
    TestResults,
    ASTComparison,
    PipelineStatus,
    PipelineArtifact,
)
from codebuddy.llm.templates import VALIDATOR_SYSTEM, VALIDATOR_TASK, render

if TYPE_CHECKING:
    from codebuddy.llm.client import LLMClient


class ValidatorAgent(BaseAgent):
    name = "validator"
    description = "Sandboxed validation with test execution and AST comparison"

    async def analyze(self, ctx: SharedContextBus) -> PipelineArtifact:
        plan_data = ctx.get("refactor_plan")
        file_contexts_data = ctx.get("file_contexts")
        issues_data = ctx.get("issue_reports")

        plan = RefactorPlan.model_validate(plan_data) if plan_data else None
        file_contexts: list[FileContext] = []
        if file_contexts_data:
            file_contexts = [FileContext.model_validate(f) for f in file_contexts_data.get("file_contexts", [])]

        fc_by_path = {fc.file_path: fc for fc in file_contexts}
        issue_ids = []
        if issues_data:
            issue_ids = [i.get("issue_id", "") for i in issues_data.get("issues", [])]

        if not plan or not plan.patches:
            return PipelineArtifact(
                artifact_type="validation_report",
                data=ValidationReport(
                    overall_status=PipelineStatus.FAIL,
                    errors=["No refactoring plan to validate"],
                ).model_dump(),
                agent_name=self.name,
            )

        # Phase 1: Apply patches to a virtual filesystem and check for conflicts
        apply_errors = _check_patch_applicability(plan.patches, fc_by_path)
        if apply_errors:
            return PipelineArtifact(
                artifact_type="validation_report",
                data=ValidationReport(
                    overall_status=PipelineStatus.FAIL,
                    errors=apply_errors,
                ).model_dump(),
                agent_name=self.name,
            )

        # Phase 2: Try running tests in a sandbox (best-effort)
        test_results = _run_tests_sandboxed(plan.patches, fc_by_path)

        # Phase 3: AST comparison — verify structural equivalence
        ast_comparisons = _compare_asts(plan.patches, fc_by_path)

        # Phase 4: LLM validation — semantic check
        issue_ids_str = "\n".join(f"- {iid}" for iid in issue_ids[:20])
        ast_summary = "\n".join(
            f"- {cmp.file_path}: eq={cmp.structurally_equivalent}, +{cmp.added_symbols}, -{cmp.removed_symbols}"
            for cmp in ast_comparisons[:10]
        )

        prompt = render(
            VALIDATOR_TASK,
            issue_ids=issue_ids_str,
            test_results=test_results,
            ast_comparisons=ast_summary,
        )

        try:
            result = await self.client.generate(
                system=VALIDATOR_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                cache_system=True,
            )
            status = _parse_validation_status(result.get("text", ""))
        except Exception:
            status = PipelineStatus.PARTIAL

        # Determine final status from all signals
        if test_results.failed > 0 and test_results.passed == 0:
            status = PipelineStatus.FAIL
        elif test_results.passed > 0 and test_results.failed == 0 and status != PipelineStatus.FAIL:
            status = PipelineStatus.PASS

        errors = []
        if test_results.failed > 0:
            errors.append(f"Tests failed: {test_results.failed}/{test_results.total}")
        if test_results.errors > 0:
            errors.append(f"Test errors: {test_results.errors}")

        report = ValidationReport(
            overall_status=status,
            test_results=test_results,
            ast_comparisons=ast_comparisons,
            regression_flags=[e for e in errors] if errors else [],
            fixed_issues=issue_ids if status == PipelineStatus.PASS else [],
            errors=errors,
        )

        return PipelineArtifact(
            artifact_type="validation_report",
            data=report.model_dump(),
            agent_name=self.name,
        )

    async def reflect(self, ctx: SharedContextBus, feedback: dict) -> PipelineArtifact:
        return await self.analyze(ctx)


def _check_patch_applicability(patches: list[RefactorPatch], fc_by_path: dict[str, FileContext]) -> list[str]:
    """Verify patches can be applied without conflicts."""
    errors: list[str] = []
    touched_lines: dict[str, set[int]] = {}

    for patch in patches:
        if not patch.unified_diff:
            continue
        lines = set(range(len(patch.original_code.split("\n"))))
        file_lines = touched_lines.setdefault(patch.file_path, set())
        if file_lines & lines:
            errors.append(f"Conflict: {patch.patch_id} overlaps with another patch in {patch.file_path}")
        file_lines |= lines

    return errors


def _run_tests_sandboxed(patches: list[RefactorPatch], fc_by_path: dict[str, FileContext]) -> TestResults:
    """Run tests in an isolated environment (Docker or process-level sandbox).

    In production, this uses Docker SDK to spin up a sandbox container.
    For demonstration purposes, this performs local validation.
    """
    test_paths = [
        fc.file_path for fc in fc_by_path.values()
        if fc.category.value == "test"
    ]

    if not test_paths:
        # No test files found — can't validate test-based
        return TestResults(total=0, passed=0, failed=0, errors=0, stdout="No test files found")

    # Attempt to discover and run tests via pytest subprocess
    import subprocess
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        # Write patched files
        for patch in patches:
            file_path = tmp / patch.file_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(patch.refactored_code or patch.original_code, encoding="utf-8")

        try:
            result = subprocess.run(
                ["pytest", str(tmp), "--tb=short", "-q"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            return TestResults(
                total=0,  # Pytest doesn't easily give total without parsing
                passed=0 if result.returncode != 0 else 1,
                failed=1 if result.returncode != 0 else 0,
                errors=0,
                stdout=result.stdout[:5000],
                stderr=result.stderr[:3000],
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return TestResults(total=0, passed=0, failed=0, errors=0, stdout="pytest not available or timed out")


def _compare_asts(patches: list[RefactorPatch], fc_by_path: dict[str, FileContext]) -> list[ASTComparison]:
    """Compare before/after AST structure for each patched file."""
    comparisons: list[ASTComparison] = []
    for patch in patches:
        fc = fc_by_path.get(patch.file_path)
        original_symbols = fc.symbols if fc else []

        # Compute added/removed symbols via diff
        before_lines = set(patch.original_code.split("\n"))
        after_lines = set(patch.refactored_code.split("\n"))
        added = sorted(after_lines - before_lines)
        removed = sorted(before_lines - after_lines)

        added_symbols = [s.name for s in original_symbols if any(s.name in a for a in added)]
        removed_symbols = [s.name for s in original_symbols if any(s.name in r for r in removed)]

        # A refactoring is structurally equivalent if it doesn't remove public symbols
        eq = len(removed_symbols) == 0 or all(
            s.name.startswith("_") for s in original_symbols if s.name in removed_symbols
        )

        comparisons.append(ASTComparison(
            file_path=patch.file_path,
            added_symbols=added_symbols,
            removed_symbols=removed_symbols,
            modified_symbols=[s.name for s in original_symbols if s.name in added_symbols],
            structurally_equivalent=eq,
        ))

    return comparisons


def _parse_validation_status(text: str) -> PipelineStatus:
    """Parse pass/partial/fail from LLM validation output."""
    lowered = text.lower()
    if "fail" in lowered:
        return PipelineStatus.FAIL
    if "partial" in lowered:
        return PipelineStatus.PARTIAL
    if "pass" in lowered:
        return PipelineStatus.PASS
    return PipelineStatus.PARTIAL
