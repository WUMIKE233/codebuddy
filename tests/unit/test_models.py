"""Unit tests for domain models."""

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
    PipelineResult,
)


class TestFileContext:
    def test_defaults(self) -> None:
        fc = FileContext(file_path="a.py", language="python", category=FileCategory.LOGIC)
        assert fc.relevance_score == 0.0
        assert fc.diff_hunks == []
        assert fc.full_content == ""

    def test_serialization(self) -> None:
        fc = FileContext(
            file_path="src/main.py",
            language="python",
            category=FileCategory.LOGIC,
            relevance_score=0.9,
        )
        data = fc.model_dump()
        assert data["file_path"] == "src/main.py"
        assert data["language"] == "python"

    def test_deserialization(self) -> None:
        data = {"file_path": "a.py", "language": "python", "category": "logic", "relevance_score": 0.5}
        fc = FileContext.model_validate(data)
        assert fc.file_path == "a.py"
        assert fc.relevance_score == 0.5


class TestIssueReport:
    def test_issue_creation(self) -> None:
        issue = IssueReport(
            file_path="a.py",
            line_range=(10, 15),
            category=IssueCategory.BUG,
            severity=Severity.CRITICAL,
            title="Null pointer",
            description="Potential null dereference",
            root_cause_chain=["Missing null check", "Crash at runtime"],
            confidence=0.95,
        )
        assert issue.issue_id
        assert len(issue.issue_id) == 12

    def test_severity_values(self) -> None:
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"


class TestRefactorPlan:
    def test_empty_plan(self) -> None:
        plan = RefactorPlan()
        assert plan.patches == []
        assert plan.ordering == []

    def test_plan_with_patches(self) -> None:
        patch = RefactorPatch(
            file_path="a.py",
            original_code="x=1",
            refactored_code="x = 1",
            pattern_applied="formatting",
        )
        plan = RefactorPlan(
            patches=[patch],
            ordering=[patch.patch_id],
            reasoning="Fix formatting",
        )
        assert len(plan.patches) == 1
        assert plan.ordering == [patch.patch_id]


class TestValidationReport:
    def test_pass(self) -> None:
        report = ValidationReport(
            overall_status=PipelineStatus.PASS,
            test_results=TestResults(total=10, passed=10),
        )
        assert report.overall_status == PipelineStatus.PASS

    def test_fail(self) -> None:
        report = ValidationReport(
            overall_status=PipelineStatus.FAIL,
            test_results=TestResults(total=10, passed=3, failed=7, errors=2),
            errors=["Multiple test failures"],
        )
        assert report.overall_status == PipelineStatus.FAIL
        assert len(report.errors) == 1


class TestPipelineResult:
    def test_empty_result(self) -> None:
        result = PipelineResult(status=PipelineStatus.PASS)
        assert result.file_contexts == []
        assert result.issues == []
        assert result.refactor_plan is None
        assert result.validation is None

    def test_json_export(self) -> None:
        result = PipelineResult(status=PipelineStatus.PASS, total_tokens=1500)
        data = result.model_dump_json(indent=2)
        assert "1500" in data
        assert "pass" in data
