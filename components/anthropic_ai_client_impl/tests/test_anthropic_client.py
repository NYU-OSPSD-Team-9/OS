"""Unit tests for the Anthropic AI client implementation."""

from unittest.mock import MagicMock, patch

import pytest
from ai_client_api.client import AiClient, AiTool, TokenUsage, _AiClientRegistry
from anthropic_ai_client_impl.client import (
    AnthropicAiClient,
    _create_anthropic_client,
    _estimate_cost_usd,
    register,
)


def setup_function() -> None:
    """Reset registry before each test."""
    _AiClientRegistry._factory = None


def test_anthropic_client_is_instance_of_ai_client() -> None:
    """AnthropicAiClient should implement AiClient."""
    client = AnthropicAiClient(api_key="test-key")
    assert isinstance(client, AiClient)


def test_register_sets_factory() -> None:
    """register() should set the factory in the registry."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        register()
    assert _AiClientRegistry.get() is not None


def test_create_anthropic_client_raises_without_key() -> None:
    """_create_anthropic_client should raise if ANTHROPIC_API_KEY not set."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            _create_anthropic_client()


def test_estimate_cost_usd_haiku() -> None:
    """Cost estimate for haiku model should be correct."""
    cost = _estimate_cost_usd("claude-3-haiku-20240307", 1000, 1000)
    assert cost > 0


def test_send_message_returns_text() -> None:
    """send_message should return text from the response."""
    client = AnthropicAiClient(api_key="test-key")
    mock_block = MagicMock()
    mock_block.text = "Hello from Claude!"
    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 5

    with patch.object(client, "_create_completion", return_value=mock_response):
        result = client.send_message("Hello")

    assert result == "Hello from Claude!"


def test_send_message_records_usage() -> None:
    """send_message should record token usage."""
    client = AnthropicAiClient(api_key="test-key")
    mock_block = MagicMock()
    mock_block.text = "reply"
    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50

    with patch.object(client, "_create_completion", return_value=mock_response):
        client.send_message("Hello")

    usage = client.get_last_usage()
    assert isinstance(usage, TokenUsage)
    assert usage.prompt_tokens == 100
    assert usage.completion_tokens == 50


def test_send_message_with_tools_stop() -> None:
    """send_message_with_tools should return text on end_turn."""
    client = AnthropicAiClient(api_key="test-key")
    mock_block = MagicMock()
    mock_block.text = "Done!"
    mock_response = MagicMock()
    mock_response.stop_reason = "end_turn"
    mock_response.content = [mock_block]
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 5

    tools = [AiTool(name="get_channels", description="List channels")]

    with patch.object(client, "_create_completion", return_value=mock_response):
        result = client.send_message_with_tools("list channels", tools)

    assert result == "Done!"


def test_get_last_usage_none_initially() -> None:
    """get_last_usage should return None before any call."""
    client = AnthropicAiClient(api_key="test-key")
    assert client.get_last_usage() is None
