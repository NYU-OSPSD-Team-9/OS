"""Unit tests for the AI client abstract interface."""

from typing import Any

import pytest
from ai_client_api.client import (
    AiClient,
    AiClientError,
    AiProviderError,
    AiResponseValidationError,
    AiTool,
    AiToolError,
    _AiClientRegistry,
    get_ai_client,
    register_ai_client,
    tool_from_function,
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
            """Return other."""
            return "other"

        def send_message_with_tools(
            self,
            prompt: str,
            tools: list[AiTool],
            context: dict[str, Any] | None = None,
        ) -> str:
            """Return other with tools."""
            return "other with tools"

    register_ai_client(MockAiClient)
    register_ai_client(OtherClient)
    client = get_ai_client()
    assert isinstance(client, OtherClient)


# ---------------------------------------------------------------------------
# Tests for structured AI outputs (extra credit)
# ---------------------------------------------------------------------------


def test_tool_from_function_generates_schema() -> None:
    """tool_from_function should auto-generate parameter schema from type hints."""
    def send_message(channel_id: str, text: str) -> str:
        """Send a message."""
        return f"{channel_id}: {text}"

    tool = tool_from_function(send_message, "Send a message to a channel")
    assert tool.name == "send_message"
    assert tool.description == "Send a message to a channel"
    assert "channel_id" in tool.parameters
    assert "text" in tool.parameters
    assert tool.parameters["channel_id"]["type"] == "string"
    assert tool.parameters["text"]["type"] == "string"
    assert tool.handler is send_message


def test_tool_from_function_maps_int_type() -> None:
    """tool_from_function should map int to integer JSON type."""
    def get_messages(channel_id: str, limit: int) -> str:
        """Get messages."""
        return f"{channel_id}: {limit}"

    tool = tool_from_function(get_messages, "Get messages")
    assert tool.parameters["limit"]["type"] == "integer"
    assert tool.parameters["channel_id"]["type"] == "string"


def test_tool_from_function_sets_handler() -> None:
    """tool_from_function should set the handler to the original function."""
    def my_func(x: str) -> str:
        """Do something."""
        return x

    tool = tool_from_function(my_func, "My function")
    assert tool.handler is my_func
    assert tool.handler("test") == "test"


def test_ai_tool_error_has_tool_name() -> None:
    """AiToolError should store the tool name."""
    err = AiToolError("send_message", "channel not found")
    assert err.tool_name == "send_message"
    assert "send_message" in str(err)
    assert "channel not found" in str(err)


def test_ai_tool_error_is_ai_client_error() -> None:
    """AiToolError should be a subclass of AiClientError."""
    err = AiToolError("tool", "msg")
    assert isinstance(err, AiClientError)


def test_ai_response_validation_error_is_ai_client_error() -> None:
    """AiResponseValidationError should be a subclass of AiClientError."""
    err = AiResponseValidationError("invalid response")
    assert isinstance(err, AiClientError)


def test_ai_provider_error_is_ai_client_error() -> None:
    """AiProviderError should be a subclass of AiClientError."""
    err = AiProviderError("provider error")
    assert isinstance(err, AiClientError)


def test_validate_ai_response_returns_model() -> None:
    """validate_ai_response should return an AiTextResponse."""
    from ai_client_api.client import AiTextResponse, validate_ai_response
    result = validate_ai_response("Hello world", model="gpt-4o-mini")
    assert isinstance(result, AiTextResponse)
    assert result.text == "Hello world"
    assert result.model == "gpt-4o-mini"
    assert result.finish_reason == "stop"


def test_validate_ai_response_empty_text() -> None:
    """validate_ai_response should work with empty text."""
    from ai_client_api.client import AiTextResponse, validate_ai_response
    result = validate_ai_response("")
    assert isinstance(result, AiTextResponse)
    assert result.text == ""


def test_ai_tool_call_response_model() -> None:
    """AiToolCallResponse should validate tool call data."""
    from ai_client_api.client import AiToolCallResponse
    response = AiToolCallResponse(
        tool_name="send_message",
        arguments={"channel_id": "C123", "text": "hello"},
        result="ok",
    )
    assert response.tool_name == "send_message"
    assert response.arguments["channel_id"] == "C123"
