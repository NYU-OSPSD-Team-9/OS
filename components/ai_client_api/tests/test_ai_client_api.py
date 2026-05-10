"""Unit tests for the AI client abstract interface."""

from typing import Any

import pytest
from ai_client_api.client import (
    AiClient,
    AiTool,
    _AiClientRegistry,
    get_ai_client,
    register_ai_client,
)


def setup_function() -> None:
    """Reset registry before each test."""
    _AiClientRegistry._factory = None


class MockAiClient(AiClient):
    """Minimal AI client for testing."""

    def send_message(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Return a static mock reply."""
        return f"mock reply to: {prompt}"

    def send_message_with_tools(
        self,
        prompt: str,
        tools: list[AiTool],
        context: dict[str, Any] | None = None,
    ) -> str:
        """Return a static mock reply acknowledging tools."""
        tool_names = [t.name for t in tools]
        return f"mock reply with tools {tool_names}: {prompt}"


def test_get_ai_client_raises_when_nothing_registered() -> None:
    """get_ai_client should raise RuntimeError when no factory is registered."""
    with pytest.raises(RuntimeError, match="No AI client implementation registered"):
        get_ai_client()


def test_register_ai_client_stores_factory() -> None:
    """register_ai_client should persist the factory."""
    register_ai_client(MockAiClient)
    assert _AiClientRegistry.get() is not None


def test_get_ai_client_returns_registered_implementation() -> None:
    """get_ai_client should return an instance of the registered class."""
    register_ai_client(MockAiClient)
    client = get_ai_client()
    assert isinstance(client, MockAiClient)


def test_send_message_returns_string() -> None:
    """send_message should return a non-empty string."""
    register_ai_client(MockAiClient)
    client = get_ai_client()
    result = client.send_message("hello")
    assert isinstance(result, str)
    assert "hello" in result


def test_send_message_with_tools_includes_tool_names() -> None:
    """send_message_with_tools should invoke tool-aware logic."""
    register_ai_client(MockAiClient)
    client = get_ai_client()
    tools = [AiTool(name="send_slack_message", description="Sends a message to Slack")]
    result = client.send_message_with_tools("do something", tools)
    assert "send_slack_message" in result


def test_ai_tool_dataclass_defaults() -> None:
    """AiTool should have an empty parameters dict by default."""
    tool = AiTool(name="list_channels", description="Lists channels")
    assert tool.parameters == {}


def test_register_ai_client_replaces_previous() -> None:
    """A second register_ai_client call should replace the first factory."""

    class OtherClient(AiClient):
        def send_message(
            self, prompt: str, context: dict[str, Any] | None = None,
        ) -> str:
            return "other"

        def send_message_with_tools(
            self,
            prompt: str,
            tools: list[AiTool],
            context: dict[str, Any] | None = None,
        ) -> str:
            return "other with tools"

    register_ai_client(MockAiClient)
    register_ai_client(OtherClient)
    client = get_ai_client()
    assert isinstance(client, OtherClient)
