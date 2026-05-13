"""Scanner Agent — classifies changed files by language, category, and relevance."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from codebuddy.core.agent import BaseAgent
from codebuddy.core.context import SharedContextBus
from codebuddy.core.models import (
    FileContext,
    FileCategory,
    DiffHunk,
    PipelineArtifact,
)
from codebuddy.llm.templates import SCANNER_SYSTEM, SCANNER_TASK, render

if TYPE_CHECKING:
    from codebuddy.llm.client import LLMClient

# Quick classification heuristics (used before LLM for cost savings)
_EXT_LANGUAGE: dict[str, str] = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".sql": "sql",
    ".yaml": "yaml", ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown", ".mdx": "markdown",
    ".css": "css", ".scss": "scss", ".less": "less",
    ".html": "html", ".htm": "html",
    ".sh": "shell", ".bash": "shell",
    ".dockerfile": "dockerfile",
}


class ScannerAgent(BaseAgent):
    name = "scanner"
    description = "Classifies changed files by language, category, and relevance score"

    async def analyze(self, ctx: SharedContextBus) -> PipelineArtifact:
        diff_content = ctx.get_meta("diff_content", "")
        file_list = ctx.get_meta("file_list", [])

        # Phase 1: Parse diff hunks heuristically (no LLM cost)
        hunks_by_file = _parse_diff_hunks(diff_content)

        # Phase 2: Quick classification by file extension
        contexts: list[FileContext] = []
        for file_path in file_list or hunks_by_file:
            lang = _classify_language(file_path)
            cat = _classify_category(file_path)
            contexts.append(FileContext(
                file_path=file_path,
                language=lang,
                category=cat,
                relevance_score=_default_relevance(file_path),
                diff_hunks=hunks_by_file.get(file_path, []),
            ))

        # Phase 3: If we have a meaningful diff, use Claude for deeper classification
        if diff_content and len(contexts) <= 50:
            try:
                prompt = render(SCANNER_TASK, diff_content=diff_content[:20000], file_list=file_list)
                result = await self.client.generate(
                    system=SCANNER_SYSTEM,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4096,
                    cache_system=True,
                )
                # Merge LLM insights into FileContexts (best-effort, non-blocking)
                _merge_llm_insights(contexts, result.get("text", ""))
            except Exception:
                pass  # LLM classification is optional; heuristic baseline is fine

        return PipelineArtifact(
            artifact_type="file_contexts",
            data={"file_contexts": [c.model_dump() for c in contexts]},
            agent_name=self.name,
        )

    async def reflect(self, ctx: SharedContextBus, feedback: dict) -> PipelineArtifact:
        # Scanner doesn't benefit from loop-back; just re-run
        return await self.analyze(ctx)


# ── Diff parsing (heuristic, no LLM) ─────────────────────────────────────────

_DIFF_HUNK_RE = re.compile(
    r"^@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@(.*)$", re.MULTILINE
)


def _parse_diff_hunks(diff: str) -> dict[str, list[DiffHunk]]:
    """Parse unified diff into per-file DiffHunk lists."""
    by_file: dict[str, list[DiffHunk]] = {}
    current_file = ""
    lines = diff.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        if line.startswith("diff --git") or line.startswith("--- a/") or line.startswith("+++ b/"):
            if line.startswith("--- a/"):
                current_file = line[6:]
            elif line.startswith("+++ b/"):
                current_file = line[6:]
            i += 1
            continue

        match = _DIFF_HUNK_RE.match(line)
        if match:
            old_start = int(match.group(1))
            old_count = int(match.group(2) or 1)
            new_start = int(match.group(3))
            new_count = int(match.group(4) or 1)
            header = match.group(5).strip()

            # Collect hunk content
            hunk_lines: list[str] = [line]
            i += 1
            while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith("diff --git"):
                hunk_lines.append(lines[i])
                i += 1

            if current_file:
                by_file.setdefault(current_file, []).append(DiffHunk(
                    header=header,
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    content="\n".join(hunk_lines),
                ))
        else:
            i += 1

    return by_file


def _classify_language(file_path: str) -> str:
    for ext, lang in _EXT_LANGUAGE.items():
        if file_path.endswith(ext):
            return lang
    return "unknown"


def _classify_category(file_path: str) -> FileCategory:
    path_lower = file_path.lower()
    if "test" in path_lower or path_lower.endswith("_test.py") or path_lower.endswith(".test."):
        return FileCategory.TEST
    if any(seg in path_lower for seg in ["docs", "readme", ".md"]):
        return FileCategory.DOCS
    if any(seg in path_lower for seg in ["config", "settings", ".yaml", ".yml", ".toml", ".json", ".env"]):
        return FileCategory.CONFIG
    if any(seg in path_lower for seg in ["package.json", "requirements", "pyproject", "cargo.toml", "go.mod"]):
        return FileCategory.DEPENDENCY
    return FileCategory.LOGIC


def _default_relevance(file_path: str) -> float:
    path_lower = file_path.lower()
    if any(seg in path_lower for seg in ["test", "docs", ".md", ".txt"]):
        return 0.2
    if any(seg in path_lower for seg in ["config", ".yaml", ".yml", ".toml", ".json"]):
        return 0.4
    return 0.7


def _merge_llm_insights(contexts: list[FileContext], llm_text: str) -> None:
    """Best-effort merge of LLM classification into FileContexts. Not critical."""
    # Parse LLM text for file-level annotations and update contexts
    for ctx_item in contexts:
        if ctx_item.file_path in llm_text:
            lowered = llm_text.lower()
            if "relevance" in lowered:
                for line in llm_text.split("\n"):
                    if ctx_item.file_path in line and "relevance" in line.lower():
                        try:
                            numbers = [float(s) for s in re.findall(r"0?\.\d+", line) if float(s) <= 1.0]
                            if numbers:
                                ctx_item.relevance_score = numbers[0]
                        except ValueError:
                            pass
