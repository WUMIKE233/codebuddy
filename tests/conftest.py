"""Shared test fixtures."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock

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
)
from codebuddy.config import Config


@pytest.fixture
def context() -> SharedContextBus:
    ctx = SharedContextBus()
    ctx.set_meta("diff_content", "mock diff content")
    ctx.set_meta("file_list", ["src/main.py", "tests/test_main.py"])
    return ctx


@pytest.fixture
def sample_file_context() -> FileContext:
    return FileContext(
        file_path="src/main.py",
        language="python",
        category=FileCategory.LOGIC,
        relevance_score=0.85,
        full_content="def add(a, b):\n    return a + b\n",
        symbols=[],
    )


@pytest.fixture
def sample_issue() -> IssueReport:
    return IssueReport(
        issue_id="test-001",
        file_path="src/main.py",
        line_range=(1, 2),
        category=IssueCategory.SMELL,
        severity=Severity.MEDIUM,
        title="Missing type hints",
        description="Function add() has no type annotations",
        root_cause_chain=["Missing type annotation", "Reduced IDE support", "Harder to maintain"],
        code_snippet="def add(a, b):",
        suggested_fix="Add type hints: def add(a: int, b: int) -> int:",
        confidence=0.9,
    )


@pytest.fixture
def sample_patch() -> RefactorPatch:
    return RefactorPatch(
        patch_id="patch-001",
        issue_ids=["test-001"],
        file_path="src/main.py",
        original_code="def add(a, b):\n    return a + b",
        refactored_code="def add(a: int, b: int) -> int:\n    return a + b",
        unified_diff="@@ -1,2 +1,2 @@\n-def add(a, b):\n+def add(a: int, b: int) -> int:\n     return a + b",
        pattern_applied="add-type-hints",
        rationale="Improve code clarity and enable static type checking",
    )


@pytest.fixture
def sample_plan(sample_patch: RefactorPatch) -> RefactorPlan:
    return RefactorPlan(
        plan_id="plan-001",
        patches=[sample_patch],
        ordering=["patch-001"],
        reasoning="Simple type annotation fix",
    )


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.generate = AsyncMock(return_value={"text": "mock response"})
    client.generate_structured = AsyncMock(return_value=MagicMock())
    client.total_tokens = 0
    client.default_model = "claude-sonnet-4-5-20250514"
    return client


@pytest.fixture
def test_config() -> Config:
    return Config()
