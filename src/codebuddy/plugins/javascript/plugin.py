"""Built-in JavaScript/TypeScript plugin."""

from __future__ import annotations

from codebuddy.plugins.base import (
    PluginBase,
    ScannerRule,
    AnalyzerCheck,
    RefactoringPattern,
)


class JavaScriptPlugin(PluginBase):
    name = "javascript"
    languages = ["javascript", "typescript", "jsx", "tsx"]
    version = "0.2.0"

    def get_scanner_rules(self) -> list[ScannerRule]:
        return [
            ScannerRule(name="js-source", file_patterns=["*.js", "*.mjs", "*.cjs", "*.ts", "*.tsx", "*.jsx"]),
            ScannerRule(name="js-config", file_patterns=["package.json", "tsconfig.json", "*.config.*"]),
            ScannerRule(name="js-test", file_patterns=["*.test.*", "*.spec.*", "__tests__/**/*"]),
        ]

    def get_analyzer_checks(self) -> list[AnalyzerCheck]:
        return [
            AnalyzerCheck(
                name="js-undefined-var",
                description="Variable used before definition or import",
                category="bug", severity="critical",
            ),
            AnalyzerCheck(
                name="js-null-reference",
                description="Possible null/undefined reference — use optional chaining (?.)",
                category="bug", severity="high",
            ),
            AnalyzerCheck(
                name="js-await-no-try",
                description="await without try/catch — unhandled promise rejection",
                category="bug", severity="high",
            ),
            AnalyzerCheck(
                name="js-type-coercion",
                description="Using == instead of === leading to unexpected type coercion",
                category="bug", severity="high",
            ),
            AnalyzerCheck(
                name="js-mutating-state",
                description="Direct mutation of React state or props without setState",
                category="bug", severity="high",
            ),
            AnalyzerCheck(
                name="js-xss-innerhtml",
                description="innerHTML or dangerouslySetInnerHTML with unsanitized input — XSS risk",
                category="security", severity="critical",
            ),
            AnalyzerCheck(
                name="js-eval",
                description="eval() with dynamic input — code injection risk",
                category="security", severity="critical",
            ),
            AnalyzerCheck(
                name="js-no-array-index-key",
                description="Using array index as React key — causes reconciliation bugs",
                category="bug", severity="medium",
            ),
            AnalyzerCheck(
                name="js-missing-deps-useeffect",
                description="useEffect missing dependencies — stale closure bug",
                category="bug", severity="high",
            ),
            AnalyzerCheck(
                name="js-large-bundle-import",
                description="Importing entire library — use tree-shakeable named imports",
                category="performance", severity="low",
            ),
            AnalyzerCheck(
                name="js-unused-variable",
                description="Variable is declared but never used",
                category="style", severity="low",
            ),
            AnalyzerCheck(
                name="js-console-log",
                description="console.log left in production code",
                category="style", severity="info",
            ),
        ]

    def get_refactoring_patterns(self) -> list[RefactoringPattern]:
        return [
            RefactoringPattern(
                name="extract-component",
                description="Extract JSX into a separate React component",
                applicable_languages=["typescript", "javascript", "tsx", "jsx"],
                prompt_hint="Extract the selected JSX block into a named React component with its own props interface.",
            ),
            RefactoringPattern(
                name="optional-chaining",
                description="Replace nested null checks with optional chaining (?.)",
                applicable_languages=["typescript", "javascript"],
                prompt_hint="Replace if (obj && obj.a && obj.a.b) with obj?.a?.b using optional chaining.",
            ),
            RefactoringPattern(
                name="async-await",
                description="Convert .then() chains to async/await",
                applicable_languages=["typescript", "javascript"],
                prompt_hint="Convert the Promise .then() chain to async/await with proper try/catch.",
            ),
            RefactoringPattern(
                name="arrow-function",
                description="Convert function expressions to arrow functions where appropriate",
                applicable_languages=["typescript", "javascript"],
                prompt_hint="Replace function() {} expressions with arrow functions () => {} where this binding is not needed.",
            ),
            RefactoringPattern(
                name="destructure-props",
                description="Destructure props parameter instead of props.propName",
                applicable_languages=["typescript", "javascript", "tsx", "jsx"],
                prompt_hint="Replace props.xxx references with destructured parameters: ({ xxx, yyy }: Props).",
            ),
            RefactoringPattern(
                name="template-literal",
                description="Replace string concatenation with template literals",
                applicable_languages=["typescript", "javascript"],
                prompt_hint="Replace 'str ' + var + ' more' with `str ${var} more` using template literals.",
            ),
            RefactoringPattern(
                name="nullish-coalescing",
                description="Use ?? instead of || for default values when 0/'' are valid",
                applicable_languages=["typescript", "javascript"],
                prompt_hint="Replace || with ?? for default value assignment when falsy values like 0 or '' should be preserved.",
            ),
        ]
