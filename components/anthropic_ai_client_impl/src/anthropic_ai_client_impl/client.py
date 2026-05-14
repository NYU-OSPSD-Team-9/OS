"""Anthropic Claude implementation of AiClient."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import anthropic
from ai_client_api.client import AiClient, AiTool, TokenUsage, register_ai_client
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

_DEFAULT_MODEL = "claude-3-haiku-20240307"
_DEFAULT_MAX_TOKENS = 1024
_MAX_TOOL_ROUNDS = 5
_MAX_RETRY_ATTEMPTS = 3
_RETRY_INITIAL_WAIT_SECONDS = 0.5
_RETRY_MAX_WAIT_SECONDS = 4

logger = logging.getLogger(__name__)

_PRICE_PER_1K_TOKENS_USD: dict[str, dict[str, float]] = {
    "claude-3-haiku-20240307": {"prompt": 0.00025, "completion": 0.00125},
    "claude-3-sonnet-20240229": {"prompt": 0.00300, "completion": 0.01500},
    "claude-3-opus-20240229": {"prompt": 0.01500, "completion": 0.07500},
}

_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


def _log_retry(state: RetryCallState) -> None:
    """Log each retry attempt."""
    err = state.outcome.exception() if state.outcome else None
    logger.warning(
        "Anthropic call retry %s/%s after error: %s",
        state.attempt_number,
        _MAX_RETRY_ATTEMPTS,
        err,
    )


def _estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost for a call given token counts."""
    rates = _PRICE_PER_1K_TOKENS_USD.get(
        model,
        _PRICE_PER_1K_TOKENS_USD["claude-3-haiku-20240307"],
    )
    return round(
        (prompt_tokens / 1000.0) * rates["prompt"]
        + (completion_tokens / 1000.0) * rates["completion"],
        6,
    )


def _ai_tool_to_anthropic(tool: AiTool) -> dict[str, Any]:
    """Convert an AiTool into the Anthropic tool-calling format."""
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": {
            "type": "object",
            "properties": tool.parameters,
            "required": list(tool.parameters.keys()),
        },
    }


class AnthropicAiClient(AiClient):
    """Anthropic Claude implementation of the AiClient interface."""

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        """Initialize the Anthropic client.

        Args:
            api_key: Anthropic API key.
            model: Model identifier (e.g. claude-3-haiku-20240307).
            max_tokens: Maximum tokens in the response.

        """
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._last_usage: TokenUsage | None = None

    def get_last_usage(self) -> TokenUsage | None:
        """Return token usage captured during the most recent call."""
        return self._last_usage

    def _create_completion(self, **kwargs: Any) -> Any:
        """Call Anthropic with retry on transient errors."""
        retrying = retry(
            reraise=True,
            stop=stop_after_attempt(_MAX_RETRY_ATTEMPTS),
            wait=wait_exponential(
                multiplier=_RETRY_INITIAL_WAIT_SECONDS,
                max=_RETRY_MAX_WAIT_SECONDS,
            ),
            retry=retry_if_exception_type(_RETRYABLE_ERRORS),
            before_sleep=_log_retry,
        )

        @retrying
        def _do_call() -> Any:
            return self._client.messages.create(**kwargs)

        return _do_call()

    def _record_usage(self, response: Any) -> None:
        """Update _last_usage from an Anthropic response."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        prompt = int(getattr(usage, "input_tokens", 0) or 0)
        completion = int(getattr(usage, "output_tokens", 0) or 0)
        total = prompt + completion
        cost = _estimate_cost_usd(self._model, prompt, completion)
        self._last_usage = TokenUsage(
            model=self._model,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            estimated_cost_usd=cost,
        )

    def _build_system_prompt(self, context: dict[str, Any] | None) -> str:
        """Build a system prompt with optional context injection."""
        base = (
            "You are a helpful assistant integrated with a Slack-based chat system. "
            "You can help users manage messages, channels, and tickets."
        )
        if not context:
            return base
        context_lines = "\n".join(f"- {k}: {v}" for k, v in context.items())
        return f"{base}\n\nContext:\n{context_lines}"

    def send_message(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Send a prompt and return the text response."""
        self._last_usage = None
        system = self._build_system_prompt(context)
        response = self._create_completion(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        self._record_usage(response)
        for block in response.content:
            if hasattr(block, "text"):
                return str(block.text)
        return ""

    def send_message_with_tools(  # noqa: C901, PLR0912
        self,
        prompt: str,
        tools: list[AiTool],
        context: dict[str, Any] | None = None,
    ) -> str:
        """Send a prompt with tool definitions; resolve any tool calls."""
        self._last_usage = None
        system = self._build_system_prompt(context)
        anthropic_tools = [_ai_tool_to_anthropic(t) for t in tools]
        tool_map = {t.name: t for t in tools}
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompt},
        ]

        tool_rounds = 0
        while tool_rounds < _MAX_TOOL_ROUNDS:
            response = self._create_completion(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                tools=anthropic_tools,
                messages=messages,
            )
            self._record_usage(response)

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        return str(block.text)
                return ""

            if response.stop_reason == "tool_use":
                assistant_content = response.content
                messages.append({
                    "role": "assistant",
                    "content": [b.model_dump() for b in assistant_content],
                })
                tool_results = []
                for block in assistant_content:
                    if block.type != "tool_use":
                        continue
                    fn_name = block.name
                    fn_args = block.input or {}
                    tool = tool_map.get(fn_name)
                    if tool is not None and tool.handler is not None:
                        try:
                            result = tool.handler(**fn_args)
                        except Exception as exc:  # noqa: BLE001
                            result = json.dumps({"error": str(exc)})
                    else:
                        result = json.dumps({
                            "tool": fn_name,
                            "inputs": fn_args,
                            "status": "no_handler",
                        })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
                messages.append({"role": "user", "content": tool_results})
                tool_rounds += 1
            else:
                for block in response.content:
                    if hasattr(block, "text"):
                        return str(block.text)
                return ""

        return "Max tool rounds exceeded. Please try again."


def _create_anthropic_client() -> AnthropicAiClient:
    """Create an AnthropicAiClient from environment variables."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        msg = "ANTHROPIC_API_KEY environment variable must be set"
        raise ValueError(msg)
    model = os.getenv("ANTHROPIC_MODEL", _DEFAULT_MODEL)
    return AnthropicAiClient(api_key=api_key, model=model)


def register() -> None:
    """Register the Anthropic client factory."""
    register_ai_client(_create_anthropic_client)
