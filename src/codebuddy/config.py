"""Configuration loader — YAML files merged with environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Per-agent settings."""
    model: str = "claude-sonnet-4-5-20250514"
    max_tokens: int = 8192
    thinking_budget: int = 0
    temperature: float = 0.1


class PipelineConfig(BaseModel):
    """Configuration for a pipeline run."""
    agents: list[str] = ["scanner", "analyzer", "refactorer", "validator"]
    max_iterations: int = 3
    fail_on: str = "critical"  # severity threshold to fail fast


class ScannerConfig(AgentConfig):
    max_files_per_run: int = 200
    min_relevance: float = 0.1
    ignore_patterns: list[str] = Field(default_factory=lambda: [
        "*.lock", "*.min.js", "*.min.css", "*.map", "*.svg",
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    ])


class AnalyzerConfig(AgentConfig):
    min_confidence: float = 0.6
    max_issues_per_file: int = 20
    severity_filter: list[str] = ["critical", "high", "medium"]


class RefactorerConfig(AgentConfig):
    thinking_budget: int = 16384
    max_patches: int = 50
    max_files: int = 20


class ValidatorConfig(AgentConfig):
    sandbox_image: str = "codebuddy-sandbox:latest"
    test_timeout: int = 300
    max_test_output_bytes: int = 1_000_000


class Config(BaseModel):
    """Root configuration."""
    scanner: ScannerConfig = Field(default_factory=ScannerConfig)
    analyzer: AnalyzerConfig = Field(default_factory=AnalyzerConfig)
    refactorer: RefactorerConfig = Field(default_factory=RefactorerConfig)
    validator: ValidatorConfig = Field(default_factory=ValidatorConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    anthropic_api_key: str = ""
    github_token: str = ""
    log_level: str = "INFO"


def load_config(
    config_path: str | Path | None = None,
    profile: str = "default",
) -> Config:
    """Load configuration from a YAML file with env-var overrides."""
    data: dict[str, Any] = {}

    if config_path:
        path = Path(config_path)
    else:
        path = Path("config") / f"{profile}.yaml"

    if path.exists():
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

    # Environment variable overrides
    env_map = {
        "anthropic_api_key": "ANTHROPIC_API_KEY",
        "github_token": "GITHUB_TOKEN",
        "log_level": "CODEBUDDY_LOG_LEVEL",
    }
    for key, env in env_map.items():
        if val := os.environ.get(env):
            data[key] = val

    return Config.model_validate(data)
