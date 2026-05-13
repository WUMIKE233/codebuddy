"""Anthropic SDK wrapper — caching, retries, structured output, token tracking."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from anthropic import Anthropic, APIStatusError, APITimeoutError, RateLimitError
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class LLMClient:
    """Thin wrapper around Anthropic client with production-grade resilience."""

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "claude-sonnet-4-5-20250514",
        max_retries: int = 3,
        timeout: float = 120.0,
    ) -> None:
        self.client = Anthropic(api_key=api_key, max_retries=0, timeout=timeout)
        self.default_model = default_model
        self.max_retries = max_retries
        self._token_usage: dict[str, int] = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}

    @property
    def total_tokens(self) -> int:
        return self._token_usage["input"] + self._token_usage["output"]

    # ── Public API ──────────────────────────────────────────────────────────

    async def generate(
        self,
        system: str,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        thinking_budget: int = 0,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        cache_system: bool = True,
    ) -> dict[str, Any]:
        """Send a message to Claude and return the parsed response."""
        kwargs = self._build_request(
            system=system,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            thinking_budget=thinking_budget,
            tools=tools,
            tool_choice=tool_choice,
            cache_system=cache_system,
        )

        for attempt in range(self.max_retries + 1):
            try:
                response = await asyncio.to_thread(self.client.messages.create, **kwargs)
                self._record_usage(response)
                return self._parse_response(response)
            except RateLimitError:
                if attempt == self.max_retries:
                    raise
                wait = 2 ** attempt * 5
                logger.warning("rate_limited", attempt=attempt, wait_s=wait)
                await asyncio.sleep(wait)
            except APITimeoutError:
                if attempt == self.max_retries:
                    raise
                logger.warning("timeout", attempt=attempt)
                await asyncio.sleep(2)
            except APIStatusError as exc:
                if attempt == self.max_retries or exc.status_code < 500:
                    raise
                wait = 2 ** attempt
                logger.warning("api_error", status=exc.status_code, attempt=attempt, wait_s=wait)
                await asyncio.sleep(wait)

        raise RuntimeError("unreachable")

    async def generate_structured(
        self,
        system: str,
        messages: list[dict[str, Any]],
        output_model: type[BaseModel],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        thinking_budget: int = 0,
        cache_system: bool = True,
    ) -> BaseModel:
        """Generate and parse into a Pydantic model via tool-use."""
        schema = output_model.model_json_schema()
        tool_name = f"output_{output_model.__name__}"

        result = await self.generate(
            system=system,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            thinking_budget=thinking_budget,
            tools=[{
                "name": tool_name,
                "description": f"Return structured output as {output_model.__name__}",
                "input_schema": schema,
            }],
            tool_choice={"type": "tool", "name": tool_name},
            cache_system=cache_system,
        )

        raw = result.get("tool_input", {})
        return output_model.model_validate(raw)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _build_request(
        self,
        system: str,
        messages: list[dict[str, Any]],
        model: str | None,
        max_tokens: int,
        thinking_budget: int,
        tools: list[dict[str, Any]] | None,
        tool_choice: dict[str, Any] | None,
        cache_system: bool,
    ) -> dict[str, Any]:
        system_block: Any = system
        if cache_system:
            system_block = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "max_tokens": max_tokens,
            "messages": messages,
            "system": system_block,
        }

        if thinking_budget > 0:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
            # When thinking is enabled, max_tokens must cover thinking budget
            kwargs["max_tokens"] = max(max_tokens, thinking_budget + 1024)

        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        return kwargs

    def _parse_response(self, response: Any) -> dict[str, Any]:
        result: dict[str, Any] = {"text": "", "tool_input": None, "stop_reason": response.stop_reason}

        for block in response.content:
            if block.type == "text":
                result["text"] += block.text
            elif block.type == "tool_use":
                result["tool_input"] = block.input
            elif block.type == "thinking":
                result["thinking"] = block.thinking
                if hasattr(block, "signature"):
                    result["signature"] = block.signature

        return result

    def _record_usage(self, response: Any) -> None:
        usage = response.usage
        self._token_usage["input"] += usage.input_tokens
        self._token_usage["output"] += usage.output_tokens
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        self._token_usage["cache_read"] += cache_read
        self._token_usage["cache_write"] += cache_write


# ── Singleton convenience ─────────────────────────────────────────────────────

_client: LLMClient | None = None


def get_client(api_key: str | None = None, **kwargs: Any) -> LLMClient:
    global _client
    if _client is None or api_key is not None:
        _client = LLMClient(api_key=api_key, **kwargs)
    return _client
