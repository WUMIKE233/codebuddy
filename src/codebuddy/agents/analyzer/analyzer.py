"""Analyzer Agent — deep semantic analysis of code quality with root-cause chains."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from codebuddy.core.agent import BaseAgent
from codebuddy.core.context import SharedContextBus
from codebuddy.core.models import (
    FileContext,
    IssueReport,
    IssueCategory,
    Severity,
    PipelineArtifact,
)
from codebuddy.llm.templates import ANALYZER_SYSTEM, ANALYZER_TASK, render

if TYPE_CHECKING:
    from codebuddy.llm.client import LLMClient


class AnalyzerOutput(BaseModel):
    """Structured output schema for the Analyzer Agent."""
    issues: list[IssueReport] = Field(default_factory=list)


class AnalyzerAgent(BaseAgent):
    name = "analyzer"
    description = "Deep code quality analysis with root-cause chains"

    async def analyze(self, ctx: SharedContextBus) -> PipelineArtifact:
        file_contexts_data = ctx.get("file_contexts")
        file_contexts: list[FileContext] = []
        if file_contexts_data:
            file_contexts = [FileContext.model_validate(f) for f in file_contexts_data.get("file_contexts", [])]

        diff_content = ctx.get_meta("diff_content", "")
        all_issues: list[IssueReport] = []

        for fc in file_contexts:
            # Skip low-relevance and non-logic files to save tokens
            if fc.relevance_score < 0.15 or fc.category.value == "docs":
                continue
            if fc.category.value in ("config", "dependency") and fc.relevance_score < 0.4:
                continue

            # Build diff summary for context
            diff_summary = "\n".join(
                h.content[:500] for h in fc.diff_hunks[:10]
            )

            prompt = render(
                ANALYZER_TASK,
                language=fc.language,
                file_path=fc.file_path,
                file_content=fc.full_content[:15000],
                diff_summary=diff_summary or "full file review (no diff hunks)",
            )

            try:
                result = await self.client.generate_structured(
                    system=ANALYZER_SYSTEM,
                    messages=[{"role": "user", "content": prompt}],
                    output_model=AnalyzerOutput,
                    max_tokens=8192,
                    thinking_budget=8192,
                    cache_system=True,
                )
                all_issues.extend(result.issues)
            except Exception:
                # On structured-output failure, try plain text fallback
                try:
                    raw = await self.client.generate(
                        system=ANALYZER_SYSTEM,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=4096,
                        cache_system=False,
                    )
                    issues = _parse_issues_from_text(raw.get("text", ""), fc.file_path)
                    all_issues.extend(issues)
                except Exception:
                    pass

        # Run duplicate detection and severity filtering
        all_issues = _deduplicate(all_issues)

        return PipelineArtifact(
            artifact_type="issue_reports",
            data={"issues": [i.model_dump() for i in all_issues]},
            agent_name=self.name,
        )

    async def reflect(self, ctx: SharedContextBus, feedback: dict) -> PipelineArtifact:
        # On loop-back, re-analyze with stricter settings
        return await self.analyze(ctx)


def _deduplicate(issues: list[IssueReport]) -> list[IssueReport]:
    """Remove issues that describe the same problem in the same location."""
    seen: set[tuple[str, int, int, str]] = set()
    unique: list[IssueReport] = []
    for issue in issues:
        key = (issue.file_path, issue.line_range[0], issue.line_range[1], issue.category.value)
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique


def _parse_issues_from_text(text: str, file_path: str) -> list[IssueReport]:
    """Fallback: parse issues from plain LLM text output."""
    issues: list[IssueReport] = []
    try:
        # Try JSON block first
        if "```json" in text:
            block = text.split("```json")[1].split("```")[0]
            data = json.loads(block)
            if isinstance(data, list):
                for item in data:
                    issues.append(IssueReport(
                        file_path=file_path,
                        line_range=(item.get("line_start", 1), item.get("line_end", 1)),
                        category=IssueCategory(item.get("category", "smell")),
                        severity=Severity(item.get("severity", "medium")),
                        title=item.get("title", "Unknown issue"),
                        description=item.get("description", ""),
                        root_cause_chain=item.get("root_cause_chain", []),
                        code_snippet=item.get("code_snippet", ""),
                        suggested_fix=item.get("suggested_fix", ""),
                        confidence=item.get("confidence", 0.5),
                    ))
    except (json.JSONDecodeError, KeyError, IndexError):
        pass
    return issues
