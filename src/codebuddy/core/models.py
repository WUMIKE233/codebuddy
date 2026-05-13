"""Domain models for the CodeBuddy pipeline — every artifact that flows between agents."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────


class FileCategory(str, Enum):
    LOGIC = "logic"
    CONFIG = "config"
    TEST = "test"
    DOCS = "docs"
    DEPENDENCY = "dependency"


class IssueCategory(str, Enum):
    BUG = "bug"
    SMELL = "smell"
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class PipelineStatus(str, Enum):
    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"


# ── Scanner outputs ──────────────────────────────────────────────────────────


class DiffHunk(BaseModel):
    """A single contiguous change in a file."""
    header: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    content: str


class SymbolInfo(BaseModel):
    """Top-level symbol in a source file (function, class, etc.)."""
    name: str
    kind: str  # function, class, method, variable
    line: int
    end_line: int | None = None


class FileContext(BaseModel):
    """Metadata and content for one file touched by a change."""
    file_path: str
    language: str
    category: FileCategory
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    diff_hunks: list[DiffHunk] = []
    full_content: str = ""
    symbols: list[SymbolInfo] = []
    dependencies: list[str] = []


# ── Analyzer outputs ─────────────────────────────────────────────────────────


class IssueReport(BaseModel):
    """A single quality issue discovered by the Analyzer Agent."""
    issue_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    file_path: str
    line_range: tuple[int, int]
    category: IssueCategory
    severity: Severity
    title: str
    description: str
    root_cause_chain: list[str] = []
    code_snippet: str = ""
    suggested_fix: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    rule_ids: list[str] = []


# ── Refactorer outputs ───────────────────────────────────────────────────────


class RefactorPatch(BaseModel):
    """A single concrete code change proposed by the Refactorer Agent."""
    patch_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    issue_ids: list[str] = []
    file_path: str
    original_code: str
    refactored_code: str
    unified_diff: str = ""
    pattern_applied: str = ""
    rationale: str = ""


class RefactorPlan(BaseModel):
    """Complete refactoring plan with ordered, non-conflicting patches."""
    plan_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    patches: list[RefactorPatch] = []
    ordering: list[str] = []
    reasoning: str = ""


# ── Validator outputs ────────────────────────────────────────────────────────


class TestResults(BaseModel):
    """Aggregated test-suite results."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    stdout: str = ""
    stderr: str = ""


class ASTComparison(BaseModel):
    """Before/after structural comparison for a single file."""
    file_path: str
    added_symbols: list[str] = []
    removed_symbols: list[str] = []
    modified_symbols: list[str] = []
    structurally_equivalent: bool = True


class ValidationReport(BaseModel):
    """Final gate report produced by the Validator Agent."""
    report_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    overall_status: PipelineStatus
    test_results: TestResults = Field(default_factory=TestResults)
    ast_comparisons: list[ASTComparison] = []
    regression_flags: list[str] = []
    fixed_issues: list[str] = []
    errors: list[str] = []


# ── Pipeline-level types ─────────────────────────────────────────────────────


class PipelineArtifact(BaseModel):
    """Wrapper for any artifact that flows through the SharedContextBus."""
    artifact_type: str
    data: dict
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_name: str = ""


class PipelineResult(BaseModel):
    """Aggregate result from a full pipeline run."""
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: PipelineStatus
    file_contexts: list[FileContext] = []
    issues: list[IssueReport] = []
    refactor_plan: RefactorPlan | None = None
    validation: ValidationReport | None = None
    iterations: int = 1
    started_at: str = ""
    finished_at: str = ""
    total_tokens: int = 0
    error: str = ""
