"""Unit tests for SharedContextBus and PipelineOrchestrator."""

from unittest.mock import MagicMock, AsyncMock, patch
import pytest

from codebuddy.core.context import SharedContextBus
from codebuddy.core.models import (
    FileContext,
    FileCategory,
    IssueReport,
    IssueCategory,
    Severity,
    RefactorPlan,
    RefactorPatch,
    ValidationReport,
    TestResults,
    PipelineStatus,
    PipelineArtifact,
)
from codebuddy.core.pipeline import PipelineOrchestrator
from codebuddy.config import Config


class TestSharedContextBus:
    def test_put_and_get(self) -> None:
        ctx = SharedContextBus()
        ctx.put("test", {"value": 42}, agent_name="test_agent")
        data = ctx.get("test")
        assert data == {"value": 42}

    def test_get_deep_copy(self) -> None:
        ctx = SharedContextBus()
        ctx.put("test", {"items": [1, 2, 3]})
        data = ctx.get("test")
        data["items"].append(4)
        # Original should be unchanged
        original = ctx.get("test")
        assert original == {"items": [1, 2, 3]}

    def test_get_missing(self) -> None:
        ctx = SharedContextBus()
        assert ctx.get("nonexistent") is None

    def test_meta(self) -> None:
        ctx = SharedContextBus()
        ctx.set_meta("key", "value")
        assert ctx.get_meta("key") == "value"
        assert ctx.get_meta("missing", "default") == "default"

    def test_log(self) -> None:
        ctx = SharedContextBus()
        ctx.put("a", {}, agent_name="agent1")
        ctx.put("b", {}, agent_name="agent2")
        log = ctx.log
        assert len(log) == 2
        assert log[0].agent_name == "agent1"
        assert log[1].agent_name == "agent2"

    def test_artifact_types(self) -> None:
        ctx = SharedContextBus()
        ctx.put("type_a", {})
        ctx.put("type_b", {})
        assert set(ctx.artifact_types) == {"type_a", "type_b"}


# ── Mock agents for pipeline test ──────────────────────────────────────────

def _make_mock_agent(name: str, artifact_type: str, output_data: dict):
    agent = MagicMock()
    agent.name = name

    async def analyze(ctx):
        return PipelineArtifact(
            artifact_type=artifact_type,
            data=output_data,
            agent_name=name,
        )

    agent.analyze = analyze
    return agent


class TestPipelineOrchestrator:
    @pytest.mark.asyncio
    async def test_full_pipeline_pass(self, test_config: Config) -> None:
        mock_llm = MagicMock()
        mock_llm.total_tokens = 5000

        agents = {
            "scanner": _make_mock_agent("scanner", "file_contexts", {
                "file_contexts": [FileContext(
                    file_path="a.py",
                    language="python",
                    category=FileCategory.LOGIC,
                    relevance_score=0.8,
                ).model_dump()],
            }),
            "analyzer": _make_mock_agent("analyzer", "issue_reports", {
                "issues": [IssueReport(
                    file_path="a.py",
                    line_range=(1, 2),
                    category=IssueCategory.SMELL,
                    severity=Severity.LOW,
                    title="Test issue",
                    description="Test",
                    confidence=0.7,
                ).model_dump()],
            }),
            "refactorer": _make_mock_agent("refactorer", "refactor_plan", {
                "patches": [RefactorPatch(
                    file_path="a.py",
                    original_code="old",
                    refactored_code="new",
                ).model_dump()],
                "ordering": [],
                "reasoning": "test",
            }),
            "validator": _make_mock_agent("validator", "validation_report", {
                "overall_status": "pass",
                "test_results": TestResults(total=5, passed=5).model_dump(),
                "ast_comparisons": [],
                "regression_flags": [],
                "fixed_issues": ["test-001"],
                "errors": [],
            }),
        }

        orchestrator = PipelineOrchestrator(test_config, mock_llm, agents)
        result = await orchestrator.run(diff_content="mock diff")

        assert result.status == PipelineStatus.PASS
        assert len(result.file_contexts) == 1
        assert len(result.issues) == 1
        assert result.refactor_plan is not None
        assert result.validation is not None
        assert result.total_tokens == 5000

    @pytest.mark.asyncio
    async def test_pipeline_scanner_failure(self, test_config: Config) -> None:
        mock_llm = MagicMock()
        mock_llm.total_tokens = 0

        scanner = MagicMock()
        scanner.name = "scanner"
        scanner.analyze = AsyncMock(side_effect=RuntimeError("Scanner failed"))

        agents = {"scanner": scanner}
        orchestrator = PipelineOrchestrator(test_config, mock_llm, agents)
        result = await orchestrator.run(diff_content="mock diff")

        assert result.status == PipelineStatus.FAIL
        assert "Scanner failed" in result.error

    @pytest.mark.asyncio
    async def test_refactor_validate_loop_max_iterations(self, test_config: Config) -> None:
        """Validator keeps failing — should stop after max_iterations."""
        mock_llm = MagicMock()
        mock_llm.total_tokens = 0

        agents = {
            "scanner": _make_mock_agent("scanner", "file_contexts", {"file_contexts": []}),
            "analyzer": _make_mock_agent("analyzer", "issue_reports", {"issues": []}),
            "refactorer": _make_mock_agent("refactorer", "refactor_plan", {"patches": [], "ordering": [], "reasoning": ""}),
            "validator": _make_mock_agent("validator", "validation_report", {
                "overall_status": "fail",
                "test_results": TestResults(total=1, passed=0, failed=1).model_dump(),
                "ast_comparisons": [],
                "regression_flags": [],
                "fixed_issues": [],
                "errors": ["Test failed"],
            }),
        }

        test_config.pipeline.max_iterations = 3
        orchestrator = PipelineOrchestrator(test_config, mock_llm, agents)
        result = await orchestrator.run(diff_content="mock diff")

        assert result.iterations == 3
        assert result.status == PipelineStatus.FAIL
