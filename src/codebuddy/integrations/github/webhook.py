"""FastAPI webhook handler for GitHub PR events."""

from __future__ import annotations

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import structlog

logger = structlog.get_logger(__name__)

app = FastAPI(title="CodeBuddy Webhook", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.post("/webhook")
async def github_webhook(request: Request) -> JSONResponse:
    """Receive GitHub webhook events and trigger the pipeline."""
    event_type = request.headers.get("X-GitHub-Event", "")

    if event_type not in ("pull_request", "pull_request_review_comment"):
        return JSONResponse({"status": "ignored", "event": event_type})

    payload = await request.json()
    action = payload.get("action", "")

    # Only trigger on PR open or sync (new commits pushed)
    if action not in ("opened", "synchronize"):
        return JSONResponse({"status": "skipped", "action": action})

    pr_number = payload.get("pull_request", {}).get("number")
    repo_name = payload.get("repository", {}).get("full_name", "")

    if not pr_number or not repo_name:
        raise HTTPException(status_code=400, detail="Missing PR number or repo name")

    logger.info(
        "webhook.received",
        event=event_type,
        action=action,
        repo=repo_name,
        pr=pr_number,
    )

    # In production, this would enqueue a pipeline job
    # For now, acknowledge the event
    return JSONResponse({
        "status": "received",
        "repo": repo_name,
        "pr": pr_number,
        "message": "Pipeline will be triggered in production deployment",
    })
