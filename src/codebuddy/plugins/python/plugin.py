"""Built-in Python plugin — PEP 8, complexity checks, security rules, refactoring patterns."""

from __future__ import annotations

from codebuddy.plugins.base import (
    PluginBase,
    ScannerRule,
    AnalyzerCheck,
    RefactoringPattern,
)


class PythonPlugin(PluginBase):
    name = "python"
    languages = ["python"]
    version = "0.2.0"

    def get_scanner_rules(self) -> list[ScannerRule]:
        return [
            ScannerRule(name="python-source", file_patterns=["*.py", "*.pyi"]),
            ScannerRule(name="python-config", file_patterns=["pyproject.toml", "setup.cfg", "setup.py", "requirements*.txt"]),
            ScannerRule(name="python-test", file_patterns=["test_*.py", "*_test.py", "tests/**/*.py"]),
        ]

    def get_analyzer_checks(self) -> list[AnalyzerCheck]:
        return [
            # Bug checks
            AnalyzerCheck(
                name="python-bare-except",
                description="Bare except: catches SystemExit and KeyboardInterrupt",
                category="bug", severity="high",
            ),
            AnalyzerCheck(
                name="python-mutable-default",
                description="Mutable default argument — shared across all calls",
                category="bug", severity="critical",
            ),
            AnalyzerCheck(
                name="python-undefined-variable",
                description="Variable may be referenced before assignment",
                category="bug", severity="critical",
            ),
            # Code smell checks
            AnalyzerCheck(
                name="python-too-many-args",
                description="Function has too many arguments (>5) — consider a dataclass or TypedDict",
                category="smell", severity="medium",
            ),
            AnalyzerCheck(
                name="python-long-function",
                description="Function is too long (>50 lines) — consider extracting helpers",
                category="smell", severity="medium",
            ),
            AnalyzerCheck(
                name="python-deep-nesting",
                description="Deeply nested control flow (>3 levels) — use early returns or extraction",
                category="smell", severity="medium",
            ),
            # Security checks
            AnalyzerCheck(
                name="python-os-system",
                description="os.system() used — prefer subprocess.run with shell=False",
                category="security", severity="high",
            ),
            AnalyzerCheck(
                name="python-eval-exec",
                description="eval() or exec() with user input — possible code injection",
                category="security", severity="critical",
            ),
            AnalyzerCheck(
                name="python-sql-injection",
                description="SQL query built with string formatting — use parameterized queries",
                category="security", severity="critical",
            ),
            AnalyzerCheck(
                name="python-hardcoded-secret",
                description="Hardcoded password, token, or API key detected",
                category="security", severity="critical",
            ),
            # Performance checks
            AnalyzerCheck(
                name="python-list-in-loop",
                description="Building a list with .append() in a loop — consider list comprehension",
                category="performance", severity="low",
            ),
            AnalyzerCheck(
                name="python-inefficient-string-cat",
                description="String concatenation in a loop — use ''.join()",
                category="performance", severity="low",
            ),
            # Style checks
            AnalyzerCheck(
                name="python-unused-import",
                description="Imported module is never used",
                category="style", severity="low",
            ),
            AnalyzerCheck(
                name="python-missing-type-hint",
                description="Public function is missing type annotations",
                category="style", severity="info",
            ),
            AnalyzerCheck(
                name="python-class-no-docstring",
                description="Public class is missing a docstring",
                category="style", severity="info",
            ),
        ]

    def get_refactoring_patterns(self) -> list[RefactoringPattern]:
        return [
            RefactoringPattern(
                name="extract-method",
                description="Extract a block of code into a named helper function",
                applicable_languages=["python"],
                prompt_hint="Extract the identified block into a separate function with a descriptive name. Keep the original function clean and readable.",
            ),
            RefactoringPattern(
                name="list-comprehension",
                description="Replace a for-loop that builds a list with a list comprehension",
                applicable_languages=["python"],
                prompt_hint="Convert the for-loop that appends to a list into an equivalent list comprehension.",
            ),
            RefactoringPattern(
                name="context-manager",
                description="Wrap resource acquisition/release in a `with` block or contextlib",
                applicable_languages=["python"],
                prompt_hint="Use a context manager (with statement) for resource handling. For custom resources, implement __enter__/__exit__ or use contextlib.contextmanager.",
            ),
            RefactoringPattern(
                name="dataclass-conversion",
                description="Convert a boilerplate class with __init__ into a @dataclass",
                applicable_languages=["python"],
                prompt_hint="Replace the verbose class with @dataclass, removing __init__, __repr__, and __eq__ boilerplate.",
            ),
            RefactoringPattern(
                name="early-return",
                description="Flatten nested conditionals with early returns",
                applicable_languages=["python"],
                prompt_hint="Restructure nested if-blocks to use early returns, reducing indentation depth.",
            ),
            RefactoringPattern(
                name="guard-clause",
                description="Move input validation to the top with guard clauses",
                applicable_languages=["python"],
                prompt_hint="Move validation checks to the function start with early returns or raises for invalid inputs.",
            ),
            RefactoringPattern(
                name="parameterize-test",
                description="Merge repetitive test functions with pytest.mark.parametrize",
                applicable_languages=["python"],
                prompt_hint="Combine multiple nearly-identical test functions into one using @pytest.mark.parametrize with a list of (input, expected) tuples.",
            ),
            RefactoringPattern(
                name="fix-bare-except",
                description="Replace bare except: with specific exception types",
                applicable_languages=["python"],
                prompt_hint="Replace `except:` with `except (ValueError, TypeError, KeyError):` or the specific exceptions the code expects.",
            ),
        ]
