"""OpenAI implementation of AiClient."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from ai_client_api.client import (
    AiClient,
    AiTool,
    AiToolError,
    TokenUsage,
    register_ai_client,
)
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_MAX_TOKENS = 1024
_MAX_TOOL_ROUNDS = int(os.getenv("OPENAI_MAX_TOOL_ROUNDS", "5"))
_MAX_RETRY_ATTEMPTS = 3
_RETRY_INITIAL_WAIT_SECONDS = 0.5
_RETRY_MAX_WAIT_SECONDS = 4

logger = logging.getLogger(__name__)

# Approximate USD per-1k-token rates for OpenAI models. Off-list models fall
# through to the gpt-4o-mini defaults so tracking does not silently zero out.
_PRICE_PER_1K_TOKENS_USD: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.00060},
    "gpt-4o": {"prompt": 0.00500, "completion": 0.01500},
    "gpt-4-turbo": {"prompt": 0.01000, "completion": 0.03000},
    "gpt-3.5-turbo": {"prompt": 0.00050, "completion": 0.00150},
}

_RETRYABLE_OPENAI_ERRORS: tuple[type[Exception], ...] = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
)


def _log_retry(state: RetryCallState) -> None:
    """Log each retry attempt so failures show up in service logs."""
    err = state.outcome.exception() if state.outcome else None
    logger.warning(
        "OpenAI call retry %s/%s after error: %s",
        state.attempt_number,
        _MAX_RETRY_ATTEMPTS,
        err,
    )


def _ai_tool_to_openai(tool: AiTool) -> dict[str, Any]:
    """Convert an AiTool into the OpenAI function-calling format."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": tool.parameters,
                "required": list(tool.parameters.keys()),
            },
        },
    }


def _estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost for a call given token counts.

    Falls back to the gpt-4o-mini rate for unknown models so dashboards do
    not silently zero out when a new model is configured.
    """
    rates = _PRICE_PER_1K_TOKENS_USD.get(
        model,
        _PRICE_PER_1K_TOKENS_USD["gpt-4o-mini"],
    )
    return round(
        (prompt_tokens / 1000.0) * rates["prompt"]
        + (completion_tokens / 1000.0) * rates["completion"],
        6,
    )


class OpenAiClient(AiClient):
    """OpenAI implementation of the AiClient interface."""

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        """Initialize the OpenAI client.

        Args:
            api_key: OpenAI API key.
            model: Model identifier (e.g. gpt-4o-mini).
            max_tokens: Maximum tokens in the response.

        """
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._last_usage: TokenUsage | None = None

    def get_last_usage(self) -> TokenUsage | None:
        """Return token usage captured during the most recent call."""
        return self._last_usage

    def _create_completion(self, **kwargs: Any) -> Any:
        """Call OpenAI with retry on transient errors.

        Wrapped via tenacity so rate-limit / timeout / connection / 5xx errors
        are retried with exponential backoff (up to ``_MAX_RETRY_ATTEMPTS``).
        """
        retrying = retry(
            reraise=True,
            stop=stop_after_attempt(_MAX_RETRY_ATTEMPTS),
            wait=wait_exponential(
                multiplier=_RETRY_INITIAL_WAIT_SECONDS,
                max=_RETRY_MAX_WAIT_SECONDS,
            ),
            retry=retry_if_exception_type(_RETRYABLE_OPENAI_ERRORS),
            before_sleep=_log_retry,
        )

        @retrying
        def _do_call() -> Any:
            return self._client.chat.completions.create(**kwargs)

        return _do_call()

    def _record_usage(self, response: Any, *, accumulate: bool) -> None:
        """Update ``_last_usage`` from an OpenAI response.

        Args:
            response: OpenAI ``ChatCompletion`` response object.
            accumulate: When True, sum onto the existing usage (used by the
                tool-calling loop, which makes multiple round-trips).

        """
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion = int(getattr(usage, "completion_tokens", 0) or 0)
        total = int(getattr(usage, "total_tokens", 0) or (prompt + completion))
        cost = _estimate_cost_usd(self._model, prompt, completion)

        if accumulate and self._last_usage is not None:
            self._last_usage = TokenUsage(
                model=self._model,
                prompt_tokens=self._last_usage.prompt_tokens + prompt,
                completion_tokens=self._last_usage.completion_tokens + completion,
                total_tokens=self._last_usage.total_tokens + total,
                estimated_cost_usd=round(
                    self._last_usage.estimated_cost_usd + cost, 6,
                ),
            )
        else:
            self._last_usage = TokenUsage(
                model=self._model,
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
                estimated_cost_usd=cost,
            )

    def send_message(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Send a prompt and return the text response.

        Args:
            prompt: The user message or instruction.
            context: Optional key-value context appended to the system prompt.

        Returns:
            Model text response.

        """
        self._last_usage = None
        system = self._build_system_prompt(context)
        response = self._create_completion(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        self._record_usage(response, accumulate=False)
        return response.choices[0].message.content or ""

    def send_message_with_tools(
        self,
        prompt: str,
        tools: list[AiTool],
        context: dict[str, Any] | None = None,
    ) -> str:
        """Send a prompt with tool definitions; resolve any tool calls the model makes.

        Args:
            prompt: The user message or instruction.
            tools: Tool definitions the model may call.
            context: Optional key-value context.

        Returns:
            Final text response after all tool calls are resolved.

        """
        self._last_usage = None
        system = self._build_system_prompt(context)
        openai_tools = [_ai_tool_to_openai(t) for t in tools]
        tool_map = {t.name: t for t in tools}
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        tool_rounds = 0
        while tool_rounds < _MAX_TOOL_ROUNDS:
            response = self._create_completion(
                model=self._model,
                max_tokens=self._max_tokens,
                tools=openai_tools,
                messages=messages,
            )
            self._record_usage(response, accumulate=True)
            choice = response.choices[0]

            if choice.finish_reason == "stop":
                return choice.message.content or ""

            if choice.finish_reason == "tool_calls":
                messages.append(choice.message.model_dump())
                for tool_call in choice.message.tool_calls or []:
                    if not hasattr(tool_call, "function"):
                        continue
                    fn_name = tool_call.function.name
                    try:
                        fn_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError as exc:
                        err_msg = f"Malformed tool arguments: {exc}"
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps({"error": err_msg}),
                        })
                        continue
                    result = self._execute_tool(fn_name, fn_args, tool_map)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
                tool_rounds += 1
            else:
                return choice.message.content or ""

        return "Max tool rounds exceeded. Please try again."

    def _execute_tool(
        self,
        name: str,
        inputs: dict[str, Any],
        tool_map: dict[str, AiTool],
    ) -> str:
        """Execute a registered domain tool.

        Args:
            name: Tool name requested by the model.
            inputs: Tool input parameters from the model.
            tool_map: Map of tool name → AiTool with optional handler.

        Returns:
            Serialised tool result as a string.

        """
        tool = tool_map.get(name)
        if tool is not None and tool.handler is not None:
            try:
                return tool.handler(**inputs)
            except (AiToolError, ValueError) as exc:
                return json.dumps({"error": str(exc)})
        return json.dumps({"tool": name, "inputs": inputs, "status": "no_handler"})

    @staticmethod
    def _build_system_prompt(context: dict[str, Any] | None) -> str:
        """Build a system prompt with optional context injection."""
        base = (
            "You are a helpful assistant integrated with a Slack-based chat system. "
            "You can help users manage messages, channels, and tickets."
        )
        if not context:
            return base
        context_lines = "\n".join(f"- {k}: {v}" for k, v in context.items())
        return f"{base}\n\nContext:\n{context_lines}"


def _create_openai_client() -> OpenAiClient:
    """Create an OpenAiClient from environment variables.

    Returns:
        OpenAiClient instance.

    Raises:
        ValueError: If OPENAI_API_KEY is not set.

    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        msg = "OPENAI_API_KEY environment variable must be set"
        raise ValueError(msg)
    model = os.getenv("OPENAI_MODEL", _DEFAULT_MODEL)
    return OpenAiClient(api_key=api_key, model=model)


# Register this implementation when module is imported
register_ai_client(_create_openai_client)
