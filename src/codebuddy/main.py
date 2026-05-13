"""CLI entry point for CodeBuddy — review, refactor, serve."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from codebuddy.config import load_config, Config
from codebuddy.llm.client import LLMClient, get_client
from codebuddy.core.pipeline import PipelineOrchestrator
from codebuddy.core.agent import BaseAgent
from codebuddy.agents.scanner.scanner import ScannerAgent
from codebuddy.agents.analyzer.analyzer import AnalyzerAgent
from codebuddy.agents.refactorer.refactorer import RefactorerAgent
from codebuddy.agents.validator.validator import ValidatorAgent

app = typer.Typer(
    name="codebuddy",
    help="Multi-Agent Code Review & Refactoring Framework powered by Claude API",
    add_completion=False,
)
console = Console()


def _build_agents(client: LLMClient) -> dict[str, BaseAgent]:
    return {
        "scanner": ScannerAgent(client),
        "analyzer": AnalyzerAgent(client),
        "refactorer": RefactorerAgent(client),
        "validator": ValidatorAgent(client),
    }


@app.command()
def review(
    diff_file: Annotated[
        Optional[Path],
        typer.Option("--diff", "-d", help="Path to a git diff file"),
    ] = None,
    repo: Annotated[
        Optional[str],
        typer.Option("--repo", "-r", help="GitHub repo (owner/name) to review"),
    ] = None,
    pr: Annotated[
        Optional[int],
        typer.Option("--pr", "-p", help="PR number to review"),
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Output path for JSON report"),
    ] = None,
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Path to config YAML"),
    ] = None,
) -> None:
    """Review code changes — find bugs, smells, and security issues."""
    config = load_config(config_path)
    _check_api_key(config)

    if diff_file:
        diff_content = diff_file.read_text(encoding="utf-8")
    elif repo and pr:
        console.print("[yellow]GitHub integration — fetching PR diff...[/]")
        diff_content = _fetch_pr_diff(config, repo, pr)
    else:
        console.print("[red]Provide --diff or --repo/--pr[/]")
        raise typer.Exit(1)

    client = get_client(api_key=config.anthropic_api_key)
    agents = _build_agents(client)
    orchestrator = PipelineOrchestrator(config, client, agents)

    console.print(Panel("[bold]CodeBuddy Review Pipeline[/]\nScanner → Analyzer", title="Running"))

    result = asyncio.run(orchestrator.run(diff_content=diff_content))

    _print_report(result)
    if output:
        output.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[green]Report saved to {output}[/]")


@app.command()
def refactor(
    diff_file: Annotated[
        Optional[Path],
        typer.Option("--diff", "-d", help="Path to a git diff file"),
    ] = None,
    repo: Annotated[
        Optional[str],
        typer.Option("--repo", "-r", help="GitHub repo (owner/name)"),
    ] = None,
    pr: Annotated[
        Optional[int],
        typer.Option("--pr", "-p", help="PR number"),
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Output path for JSON report"),
    ] = None,
    create_pr: Annotated[
        bool,
        typer.Option("--create-pr", help="Create a PR with the refactoring patches"),
    ] = False,
    config_path: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Path to config YAML"),
    ] = None,
) -> None:
    """Full pipeline: review + refactor + validate."""
    config = load_config(config_path)
    _check_api_key(config)

    if diff_file:
        diff_content = diff_file.read_text(encoding="utf-8")
    elif repo and pr:
        console.print("[yellow]Fetching PR diff from GitHub...[/]")
        diff_content = _fetch_pr_diff(config, repo, pr)
    else:
        console.print("[red]Provide --diff or --repo/--pr[/]")
        raise typer.Exit(1)

    client = get_client(api_key=config.anthropic_api_key)
    agents = _build_agents(client)
    orchestrator = PipelineOrchestrator(config, client, agents)

    console.print(Panel(
        "[bold]CodeBuddy Full Pipeline[/]\nScanner → Analyzer → Refactorer → Validator",
        title="Running",
    ))

    result = asyncio.run(orchestrator.run(diff_content=diff_content))

    _print_refactor_report(result)

    if output:
        output.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[green]Report saved to {output}[/]")

    if create_pr and repo and pr and result.refactor_plan:
        console.print("[yellow]Creating PR with refactoring patches...[/]")
        # _create_refactor_pr(config, repo, pr, result)


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host")] = "0.0.0.0",
    port: Annotated[int, typer.Option("--port")] = 8000,
    config_path: Annotated[Optional[Path], typer.Option("--config", "-c")] = None,
) -> None:
    """Start the GitHub webhook server."""
    console.print(f"[bold]Starting CodeBuddy webhook server on {host}:{port}[/]")
    console.print("[yellow]Run with: uvicorn codebuddy.integrations.github.webhook:app[/]")
    console.print(f"[yellow]  uvicorn codebuddy.integrations.github.webhook:app --host {host} --port {port}[/]")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _check_api_key(config: Config) -> None:
    if not config.anthropic_api_key:
        console.print("[red]Set ANTHROPIC_API_KEY or add anthropic_api_key to config[/]")
        raise typer.Exit(1)


def _fetch_pr_diff(config: Config, repo: str, pr: int) -> str:
    """Fetch a PR diff from GitHub."""
    try:
        from codebuddy.integrations.github.client import GitHubClient
        gh = GitHubClient(token=config.github_token)
        return gh.get_pr_diff(repo, pr)
    except Exception as exc:
        console.print(f"[red]Failed to fetch PR: {exc}[/]")
        raise typer.Exit(1)


def _print_report(result) -> None:
    """Pretty-print a review report with Rich."""
    table = Table(title="Code Review Results")
    table.add_column("Severity", style="bold")
    table.add_column("File")
    table.add_column("Issue")
    table.add_column("Root Cause Chain")

    for issue in result.issues:
        sev_color = {"critical": "red", "high": "orange1", "medium": "yellow", "low": "dim", "info": "dim"}
        color = sev_color.get(issue.severity.value if hasattr(issue.severity, 'value') else str(issue.severity), "white")
        chain = " → ".join(issue.root_cause_chain[:3]) if issue.root_cause_chain else "-"
        table.add_row(
            f"[{color}]{issue.severity.value}[/]",
            issue.file_path,
            issue.title,
            chain[:80],
        )

    console.print(table)
    console.print(f"[bold]Total issues:[/] {len(result.issues)}")
    console.print(f"[bold]Tokens used:[/] {result.total_tokens}")
    console.print(f"[bold]Iterations:[/] {result.iterations}")


def _print_refactor_report(result) -> None:
    """Pretty-print a refactoring report."""
    _print_report(result)

    if result.validation:
        val = result.validation
        status_color = {"pass": "green", "partial": "yellow", "fail": "red"}
        color = status_color.get(val.overall_status.value, "white")
        console.print(f"\n[bold]Validation:[/] [{color}]{val.overall_status.value.upper()}[/]")
        console.print(f"[bold]Tests:[/] {val.test_results.passed}/{val.test_results.total} passed")

    if result.refactor_plan:
        console.print(f"\n[bold]Patches generated:[/] {len(result.refactor_plan.patches)}")
        for patch in result.refactor_plan.patches[:10]:
            console.print(f"  - {patch.file_path}: {patch.pattern_applied or 'custom fix'}")


if __name__ == "__main__":
    app()
