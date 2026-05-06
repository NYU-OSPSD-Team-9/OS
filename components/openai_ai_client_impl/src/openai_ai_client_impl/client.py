"""OpenAI implementation of AiClient."""

from __future__ import annotations

import json
import os
from typing import Any

from ai_client_api.client import AiClient, AiTool, register_ai_client
from openai import OpenAI

_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_MAX_TOKENS = 1024
_MAX_TOOL_ROUNDS = 5


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
            },
        },
    }


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
        system = self._build_system_prompt(context)
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
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
        system = self._build_system_prompt(context)
        openai_tools = [_ai_tool_to_openai(t) for t in tools]
        tool_map = {t.name: t for t in tools}
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        tool_rounds = 0
        while tool_rounds < _MAX_TOOL_ROUNDS:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_tokens,
                tools=openai_tools,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
            )
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
            except Exception as exc:  # noqa: BLE001
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
