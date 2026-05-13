"""Jinja2 prompt template engine with built-in templates for each agent."""

from __future__ import annotations

from jinja2 import Environment, BaseLoader, Template

_env = Environment(loader=BaseLoader(), autoescape=False)

# ── Scanner templates ────────────────────────────────────────────────────────

SCANNER_SYSTEM = """\
You are a code-discovery specialist. Analyze git diffs to classify changed files.

For each file determine:
- **language**: the programming language
- **category**: one of logic, config, test, docs, dependency
- **relevance_score**: 0.0-1.0 indicating how likely this change contains bugs
- **symbols**: top-level functions, classes, methods with their line ranges

Be precise and conservative — only flag what you are confident about."""

SCANNER_TASK = """\
Review this git diff and produce a structured classification for every changed file.

Diff:
```
{{ diff_content }}
```

Full file list: {{ file_list }}"""

# ── Analyzer templates ───────────────────────────────────────────────────────

ANALYZER_SYSTEM = """\
You are a world-class code reviewer. Analyze code for bugs, smells, security issues,
performance problems, and style violations.

For each issue produce:
- **category**: bug, smell, security, performance, style
- **severity**: critical, high, medium, low, info
- **root_cause_chain**: step-by-step reasoning from symptom to root cause
- **suggested_fix**: high-level direction (not actual code)
- **confidence**: 0.0-1.0

Focus on issues that matter. Skip nitpicks. Each issue must have a clear root-cause chain
showing WHY it is a problem, not just WHAT is wrong."""

ANALYZER_TASK = """\
Analyze this file for quality issues.

Language: {{ language }}
File: {{ file_path }}

```
{{ file_content }}
```

Context: this file was changed in a PR. The diff hunks are:
```
{{ diff_summary }}
```"""

# ── Refactorer templates ─────────────────────────────────────────────────────

REFACTORER_SYSTEM = """\
You are an expert software refactoring engineer. Transform issue reports into precise,
minimal code changes. Generate exact unified diffs that apply cleanly with `git apply`.

Rules:
- Each patch must be minimal — change only what is needed to fix the issue
- Preserve existing code style and idioms
- Order patches so they don't conflict (no two patches touch the same lines)
- Each patch must include a rationale explaining the change

Output the complete refactored file content for each changed file, plus a unified diff."""

REFACTORER_TASK = """\
Generate refactoring patches for these issues.

Language: {{ language }}
File: {{ file_path }}

Current file content:
```
{{ file_content }}
```

Issues to fix:
{% for issue in issues %}
- [{{ issue.severity }}] {{ issue.title }} (lines {{ issue.line_range[0] }}-{{ issue.line_range[1] }})
  Root cause: {{ issue.root_cause_chain | join(" → ") }}
  Suggested direction: {{ issue.suggested_fix }}
{% endfor %}

Generate refactoring patches that resolve ALL issues with minimal, safe changes."""

# ── Validator templates ──────────────────────────────────────────────────────

VALIDATOR_SYSTEM = """\
You are a validation engineer. Given a set of code changes and test results,
determine whether the refactoring is safe to merge.

Evaluate:
1. Do the test results show regressions?
2. Are the AST changes structurally equivalent (same public API)?
3. Were the original issues actually fixed?
4. Were any new issues introduced?

Be conservative — if unsure, flag as partial/fail."""

VALIDATOR_TASK = """\
Evaluate this refactoring result.

Issues attempted to fix:
{% for issue_id in issue_ids %}- {{ issue_id }}
{% endfor %}

Test results:
- Total: {{ test_results.total }}
- Passed: {{ test_results.passed }}
- Failed: {{ test_results.failed }}
- Errors: {{ test_results.errors }}

Test output:
```
{{ test_results.stdout }}
{{ test_results.stderr }}
```

AST comparison summary:
{% for cmp in ast_comparisons %}
- {{ cmp.file_path }}: structurally_equivalent={{ cmp.structurally_equivalent }}
  added={{ cmp.added_symbols }}, removed={{ cmp.removed_symbols }}, modified={{ cmp.modified_symbols }}
{% endfor %}

Determine: pass, partial, or fail?"""

# ── Template access ──────────────────────────────────────────────────────────


def render(template_str: str, **kwargs: object) -> str:
    """Render a Jinja2 template string with the given variables."""
    tmpl: Template = _env.from_string(template_str)
    return tmpl.render(**kwargs)
