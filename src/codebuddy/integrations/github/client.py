"""GitHub integration — PyGithub wrapper for PR management and diff fetching."""

from __future__ import annotations

from github import Github, PullRequest, Repository


class GitHubClient:
    """Thin wrapper around PyGithub for PR operations."""

    def __init__(self, token: str) -> None:
        self.gh = Github(token)
        self.token = token

    def get_repo(self, repo_name: str) -> Repository.Repository:
        """Get a repository by owner/name."""
        return self.gh.get_repo(repo_name)

    def get_pr_diff(self, repo_name: str, pr_number: int) -> str:
        """Fetch the unified diff for a pull request."""
        repo = self.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        return pr.diff_url or ""

    def get_pr_files(self, repo_name: str, pr_number: int) -> list[str]:
        """Get list of file paths changed in a PR."""
        repo = self.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        return [f.filename for f in pr.get_files()]

    def get_pr(self, repo_name: str, pr_number: int) -> PullRequest.PullRequest:
        repo = self.get_repo(repo_name)
        return repo.get_pull(pr_number)

    def create_pr_comment(self, repo_name: str, pr_number: int, body: str) -> None:
        """Add a general comment to a PR."""
        pr = self.get_pr(repo_name, pr_number)
        pr.create_issue_comment(body)

    def create_review(
        self,
        repo_name: str,
        pr_number: int,
        body: str,
        comments: list[dict] | None = None,
        event: str = "COMMENT",
    ) -> None:
        """Create a pull request review with optional inline comments."""
        pr = self.get_pr(repo_name, pr_number)
        if comments:
            pr.create_review(body=body, comments=comments, event=event)
        else:
            pr.create_review(body=body, event=event)

    def create_branch(self, repo_name: str, branch_name: str, base_sha: str) -> None:
        """Create a new branch from a base SHA."""
        repo = self.get_repo(repo_name)
        repo.create_git_ref(f"refs/heads/{branch_name}", base_sha)

    def create_pr(
        self,
        repo_name: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
    ) -> PullRequest.PullRequest:
        """Create a new pull request."""
        repo = self.get_repo(repo_name)
        return repo.create_pull(title=title, body=body, head=head_branch, base=base_branch)
