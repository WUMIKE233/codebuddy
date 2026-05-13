#!/usr/bin/env python3
"""Demo script — runs the full CodeBuddy pipeline on a sample codebase with known issues."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Add src to path for demo runs
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from codebuddy.config import Config, load_config
from codebuddy.llm.client import LLMClient
from codebuddy.core.pipeline import PipelineOrchestrator
from codebuddy.agents.scanner.scanner import ScannerAgent
from codebuddy.agents.analyzer.analyzer import AnalyzerAgent
from codebuddy.agents.refactorer.refactorer import RefactorerAgent
from codebuddy.agents.validator.validator import ValidatorAgent


# ── Sample code with known issues ──────────────────────────────────────────

SAMPLE_PYTHON_DIFF = """\
diff --git a/src/user_service.py b/src/user_service.py
index 0000000..1111111 100644
--- a/src/user_service.py
+++ b/src/user_service.py
@@ -1,10 +1,15 @@
 import os
+import json

-def get_user(user_id):
+def get_user(user_id, db=None):
+    if db is None:
+        db = []
     try:
-        return db.query(User).filter_by(id=user_id).first()
+        query = "SELECT * FROM users WHERE id = " + user_id
+        return db.execute(query)
     except:
-        pass
+        print("error")
+        return None

 class User:
     def __init__(self, name, age):
@@ -12,3 +17,6 @@ class User:
         self.age = age

     def get_details(self):
-        return f"{self.name} ({self.age})"
+        result = ""
+        for part in [self.name, str(self.age)]:
+            result += part + " "
+        return result.strip()
"""

SAMPLE_FILE_CONTENTS = {
    "src/user_service.py": '''\
import os
import json

def get_user(user_id, db=None):
    if db is None:
        db = []
    try:
        query = "SELECT * FROM users WHERE id = " + user_id
        return db.execute(query)
    except:
        print("error")
        return None

class User:
    def __init__(self, name, age):
        self.name = name
        self.age = age

    def get_details(self):
        result = ""
        for part in [self.name, str(self.age)]:
            result += part + " "
        return result.strip()
''',
}


# ── Demo runner ────────────────────────────────────────────────────────────


def _build_agents(client: LLMClient):
    return {
        "scanner": ScannerAgent(client),
        "analyzer": AnalyzerAgent(client),
        "refactorer": RefactorerAgent(client),
        "validator": ValidatorAgent(client),
    }


def run_offline_demo() -> dict:
    """Run a demo without calling the Claude API (uses mock data)."""
    from codebuddy.core.context import SharedContextBus
    from codebuddy.core.models import (
        FileContext, FileCategory, IssueReport, IssueCategory, Severity,
        RefactorPlan, RefactorPatch, ValidationReport, TestResults,
        PipelineStatus, PipelineResult,
    )

    print("=" * 60)
    print("  CodeBuddy — Offline Demo (No API calls)")
    print("=" * 60)

    # Simulate Scanner
    print("\n[1/4] Scanner Agent: classifying files...")
    file_contexts = [
        FileContext(
            file_path="src/user_service.py",
            language="python",
            category=FileCategory.LOGIC,
            relevance_score=0.9,
            full_content=SAMPLE_FILE_CONTENTS["src/user_service.py"],
            symbols=[],
        )
    ]
    print(f"  -> Found {len(file_contexts)} file(s) to analyze")

    # Simulate Analyzer
    print("\n[2/4] Analyzer Agent: detecting issues...")
    issues = [
        IssueReport(
            issue_id="demo-001",
            file_path="src/user_service.py",
            line_range=(9, 9),
            category=IssueCategory.SECURITY,
            severity=Severity.CRITICAL,
            title="SQL injection via string concatenation",
            description="User ID is directly concatenated into SQL query without sanitization.",
            root_cause_chain=[
                "User input flows into SQL query",
                "String concatenation bypasses parameterization",
                "Attacker can inject arbitrary SQL commands",
                "Database compromise risk",
            ],
            code_snippet='query = "SELECT * FROM users WHERE id = " + user_id',
            suggested_fix="Use parameterized query: db.execute('SELECT * FROM users WHERE id = ?', (user_id,))",
            confidence=0.98,
            rule_ids=["python-sql-injection"],
        ),
        IssueReport(
            issue_id="demo-002",
            file_path="src/user_service.py",
            line_range=(10, 11),
            category=IssueCategory.BUG,
            severity=Severity.HIGH,
            title="Bare except clause catches SystemExit and KeyboardInterrupt",
            description="Bare `except:` catches all exceptions including system signals.",
            root_cause_chain=[
                "Bare except has no exception type filter",
                "SystemExit and KeyboardInterrupt are caught",
                "Application cannot be cleanly terminated",
                "Bugs are silently swallowed",
            ],
            code_snippet="except:\n    print('error')",
            suggested_fix="Use `except Exception:` or specific exception types",
            confidence=0.95,
            rule_ids=["python-bare-except"],
        ),
        IssueReport(
            issue_id="demo-003",
            file_path="src/user_service.py",
            line_range=(4, 5),
            category=IssueCategory.BUG,
            severity=Severity.CRITICAL,
            title="Mutable default argument `db=None` with list assignment",
            description="`db=[]` in default argument (from None assignment) creates shared mutable state.",
            root_cause_chain=[
                "if db is None: db = [] creates list in function body",
                "While safer than db=[], it still risks confusion",
                "Not actually a bug here, but the function signature is misleading",
            ],
            code_snippet="def get_user(user_id, db=None):\n    if db is None:\n        db = []",
            suggested_fix="Consider removing the db parameter if it's always a list",
            confidence=0.75,
            rule_ids=["python-mutable-default"],
        ),
        IssueReport(
            issue_id="demo-004",
            file_path="src/user_service.py",
            line_range=(17, 19),
            category=IssueCategory.PERFORMANCE,
            severity=Severity.LOW,
            title="Inefficient string concatenation in loop",
            description="String building with += in a loop is O(n^2).",
            root_cause_chain=[
                "Strings are immutable in Python",
                "Each += creates a new string and copies all content",
                "For large strings this becomes O(n^2)",
            ],
            code_snippet="for part in [self.name, str(self.age)]:\n    result += part + ' '",
            suggested_fix="Use ' '.join(str(p) for p in [...]) or f-string",
            confidence=0.85,
            rule_ids=["python-inefficient-string-cat"],
        ),
    ]
    for issue in issues:
        sev = issue.severity.value.upper()
        print(f"  [{sev}] {issue.file_path}:{issue.line_range[0]}: {issue.title}")
    print(f"  -> Found {len(issues)} issue(s)")

    # Simulate Refactorer
    print("\n[3/4] Refactorer Agent: generating patches...")
    patches = [
        RefactorPatch(
            patch_id="demo-patch-001",
            issue_ids=["demo-001"],
            file_path="src/user_service.py",
            original_code='query = "SELECT * FROM users WHERE id = " + user_id',
            refactored_code='query = "SELECT * FROM users WHERE id = ?"\n        result = db.execute(query, (user_id,))',
            unified_diff="""@@ -7,4 +7,4 @@
-        query = "SELECT * FROM users WHERE id = " + user_id
-        return db.execute(query)
+        query = "SELECT * FROM users WHERE id = ?"
+        return db.execute(query, (user_id,))
""",
            pattern_applied="parameterize-query",
            rationale="Prevent SQL injection by using parameterized queries.",
        ),
        RefactorPatch(
            patch_id="demo-patch-002",
            issue_ids=["demo-002"],
            file_path="src/user_service.py",
            original_code="    except:\n        print('error')\n        return None",
            refactored_code="    except Exception as e:\n        print(f'Error: {e}')\n        return None",
            unified_diff="""@@ -10,3 +10,3 @@
-    except:
-        print("error")
+    except Exception as e:
+        print(f"Error: {e}")
""",
            pattern_applied="fix-bare-except",
            rationale="Catch Exception instead of bare except to allow system signals through.",
        ),
        RefactorPatch(
            patch_id="demo-patch-003",
            issue_ids=["demo-004"],
            file_path="src/user_service.py",
            original_code='        result = ""\n        for part in [self.name, str(self.age)]:\n            result += part + " "\n        return result.strip()',
            refactored_code='        return f"{self.name} ({self.age})"',
            unified_diff="""@@ -17,5 +17,1 @@
-        result = ""
-        for part in [self.name, str(self.age)]:
-            result += part + " "
-        return result.strip()
+        return f"{self.name} ({self.age})"
""",
            pattern_applied="template-literal",
            rationale="Use f-string for efficient and readable string formatting.",
        ),
    ]

    plan = RefactorPlan(
        plan_id="demo-plan-001",
        patches=patches,
        ordering=["demo-patch-001", "demo-patch-002", "demo-patch-003"],
        reasoning="Fix SQL injection first (critical), then bare except (high), then performance (low). No conflicts as they touch different lines.",
    )
    print(f"  -> Generated {len(patches)} patch(es):")
    for p in patches:
        print(f"     - {p.patch_id}: {p.pattern_applied} ({p.file_path})")

    # Simulate Validator
    print("\n[4/4] Validator Agent: verifying changes...")
    test_results = TestResults(total=8, passed=8, failed=0, errors=0, stdout="8 passed in 0.15s")
    report = ValidationReport(
        overall_status=PipelineStatus.PASS,
        test_results=test_results,
        ast_comparisons=[],
        regression_flags=[],
        fixed_issues=["demo-001", "demo-002", "demo-004"],
        errors=[],
    )

    result = PipelineResult(
        run_id="demo-run-001",
        status=PipelineStatus.PASS,
        file_contexts=file_contexts,
        issues=issues,
        refactor_plan=plan,
        validation=report,
        iterations=1,
        total_tokens=0,  # Offline demo
    )

    # Print summary
    print(f"\n  Validation: [PASS]")
    print(f"  Tests: {test_results.passed}/{test_results.total} passed")
    print(f"  Issues fixed: {report.fixed_issues}")

    print("\n" + "=" * 60)
    print("  Pipeline Complete!")
    print(f"  Status: {result.status.value.upper()}")
    print(f"  Issues Found: {len(issues)}")
    print(f"  Patches Generated: {len(patches)}")
    print(f"  Issues Fixed: {len(report.fixed_issues)}")
    print("=" * 60)

    return result.model_dump()


def run_live_demo() -> dict | None:
    """Run the demo with real Claude API calls. Requires ANTHROPIC_API_KEY."""
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set — running offline demo instead.")
        return run_offline_demo()

    print("=" * 60)
    print("  CodeBuddy — Live Demo (Real Claude API)")
    print("=" * 60)

    config = load_config()
    config.anthropic_api_key = os.environ["ANTHROPIC_API_KEY"]

    client = LLMClient(api_key=config.anthropic_api_key)
    agents = _build_agents(client)
    orchestrator = PipelineOrchestrator(config, client, agents)

    result = asyncio.run(orchestrator.run(
        diff_content=SAMPLE_PYTHON_DIFF,
        file_list=["src/user_service.py"],
    ))

    output = result.model_dump()
    print(f"\nStatus: {result.status.value.upper()}")
    print(f"Issues: {len(result.issues)}")
    print(f"Tokens: {result.total_tokens}")
    return output


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CodeBuddy Demo")
    parser.add_argument("--live", action="store_true", help="Run with real Claude API calls")
    parser.add_argument("--output", "-o", type=str, help="Save report to JSON file")
    args = parser.parse_args()

    if args.live:
        report = run_live_demo()
    else:
        report = run_offline_demo()

    if report and args.output:
        Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport saved to {args.output}")
