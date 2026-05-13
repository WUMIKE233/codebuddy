"""Local git operations via GitPython."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterator

from git import Repo, GitCommandError


def clone_temp(url: str) -> Repo:
    """Clone a repository to a temporary directory."""
    tmpdir = tempfile.mkdtemp(prefix="codebuddy_")
    return Repo.clone_from(url, tmpdir)


def get_default_branch(repo: Repo) -> str:
    """Detect the default branch name (main or master)."""
    for branch in repo.branches:
        if branch.name in ("main", "master"):
            return branch.name
    return repo.active_branch.name


def create_work_branch(repo: Repo, base: str, prefix: str = "codebuddy/refactor") -> str:
    """Create a new branch from base and return its name."""
    branch_name = f"{prefix}_{_short_hash(repo.head.commit.hexsha)}"
    repo.create_head(branch_name, repo.commit(base))
    return branch_name


def apply_patches(repo: Repo, patches: list[dict]) -> list[str]:
    """Apply a list of patches to the working tree. Returns error messages."""
    errors: list[str] = []
    for patch in patches:
        file_path = repo.working_dir / patch["file_path"]
        if file_path.exists():
            file_path.write_text(patch["refactored_code"] or patch["original_code"], encoding="utf-8")
        else:
            errors.append(f"File not found: {patch['file_path']}")
    return errors


def commit_changes(repo: Repo, message: str) -> str | None:
    """Stage all changes and commit. Returns None on success, error message on failure."""
    try:
        repo.git.add(A=True)
        repo.git.commit("-m", message)
        return None
    except GitCommandError as exc:
        return str(exc)


def _short_hash(hexsha: str) -> str:
    return hexsha[:8]
