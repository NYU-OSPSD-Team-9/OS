"""Unit tests for OpenAI AI client implementation."""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest import mock

import pytest
from ai_client_api.client import AiTool, _AiClientRegistry
from openai_ai_client_impl.client import (
    OpenAiClient,
    _create_openai_client,
)


def setup_function() -> None:
    """Reset AI client registry before each test."""
    _AiClientRegistry._factory = None


def test_openai_client_initialization() -> None:
    """Test that OpenAiClient stores the api_key."""
    client = OpenAiClient("test-key")
    assert client._client.api_key == "test-key"


def test_send_message_returns_text() -> None:
    """send_message should return the model's text content."""
    client = OpenAiClient("test-key")
    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Hello from AI"),
                finish_reason="stop",
            ),
        ],
    )
    with mock.patch.object(
        client._client.chat.completions,
        "create",
        return_value=fake_response,
    ):
        result = client.send_message("say hello")
        assert result == "Hello from AI"


def test_send_message_with_no_content_returns_empty() -> None:
    """send_message should return empty string when content is None."""
    client = OpenAiClient("test-key")
    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None),
                finish_reason="stop",
            ),
        ],
    )
    with mock.patch.object(
        client._client.chat.completions,
        "create",
        return_value=fake_response,
    ):
        result = client.send_message("say hello")
        assert result == ""


def test_send_message_with_tools_stop_returns_content() -> None:
    """send_message_with_tools should return text on finish_reason=stop."""
    client = OpenAiClient("test-key")
    fake_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Done", tool_calls=None, model_dump=dict,
                ),
                finish_reason="stop",
            ),
        ],
    )
    with mock.patch.object(
        client._client.chat.completions,
        "create",
        return_value=fake_response,
    ):
        result = client.send_message_with_tools("do something", tools=[])
        assert result == "Done"


def test_send_message_with_tools_calls_handler() -> None:
    """When model issues a tool_call, the handler should be invoked."""
    client = OpenAiClient("test-key")
    handler_called: list[str] = []

    def my_handler(channel_id: str) -> str:
        handler_called.append(channel_id)
        return '["#general"]'

    tool = AiTool(
        name="get_channels",
        description="list channels",
        parameters={},
        handler=my_handler,
    )

    tool_call = SimpleNamespace(
        id="call_abc",
        function=SimpleNamespace(
            name="get_channels",
            arguments='{"channel_id": "C001"}',
        ),
    )
    first_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[tool_call],
                    model_dump=lambda: {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [],
                    },
                ),
                finish_reason="tool_calls",
            ),
        ],
    )
    second_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Here are your channels", tool_calls=None,
                ),
                finish_reason="stop",
            ),
        ],
    )
    with mock.patch.object(
        client._client.chat.completions,
        "create",
        side_effect=[first_response, second_response],
    ):
        result = client.send_message_with_tools("list channels", tools=[tool])
        assert result == "Here are your channels"
        assert handler_called == ["C001"]


def test_execute_tool_no_handler_returns_json() -> None:
    """_execute_tool with no handler should return a no_handler JSON."""
    client = OpenAiClient("test-key")
    tool = AiTool(name="noop", description="noop", parameters={})
    result = client._execute_tool("noop", {}, {"noop": tool})
    assert "no_handler" in result


def test_execute_tool_handler_unexpected_exception_propagates() -> None:
    """Unexpected handler exceptions should propagate to middleware."""
    client = OpenAiClient("test-key")

    def bad_handler() -> str:
        msg = "boom"
        raise RuntimeError(msg)

    tool = AiTool(name="boom", description="boom", parameters={}, handler=bad_handler)
    with pytest.raises(RuntimeError, match="boom"):
        client._execute_tool("boom", {}, {"boom": tool})


def test_create_openai_client_with_key() -> None:
    """Factory creates a client when OPENAI_API_KEY is set."""
    with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        client = _create_openai_client()
        assert isinstance(client, OpenAiClient)


def test_create_openai_client_without_key_raises() -> None:
    """Factory raises ValueError when OPENAI_API_KEY is missing."""
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(
            ValueError,
            match="OPENAI_API_KEY environment variable must be set",
        ):
            _create_openai_client()


# ---------------------------------------------------------------------------
# Token telemetry (extra credit)
# ---------------------------------------------------------------------------


def _stop_response_with_usage(
    *,
    content: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            ),
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


def test_send_message_records_token_usage() -> None:
    """send_message should populate get_last_usage from the response."""
    client = OpenAiClient("test-key", model="gpt-4o-mini")
    fake = _stop_response_with_usage(
        content="hi", prompt_tokens=20, completion_tokens=5,
    )
    with mock.patch.object(
        client._client.chat.completions, "create", return_value=fake,
    ):
        client.send_message("hello")

    usage = client.get_last_usage()
    assert usage is not None
    assert usage.model == "gpt-4o-mini"
    assert usage.prompt_tokens == 20
    assert usage.completion_tokens == 5
    assert usage.total_tokens == 25
    # 20/1000 * 0.00015 + 5/1000 * 0.00060 = 0.000003 + 0.000003 = 0.000006
    assert usage.estimated_cost_usd == pytest.approx(0.000006, abs=1e-7)


def test_send_message_with_tools_accumulates_usage_across_rounds() -> None:
    """Token usage should be summed across each round of the tool-call loop."""
    client = OpenAiClient("test-key", model="gpt-4o-mini")

    tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="ping", arguments="{}"),
    )
    round_one = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[tool_call],
                    model_dump=lambda: {"role": "assistant", "tool_calls": []},
                ),
                finish_reason="tool_calls",
            ),
        ],
        usage=SimpleNamespace(
            prompt_tokens=100, completion_tokens=20, total_tokens=120,
        ),
    )
    round_two = _stop_response_with_usage(
        content="done", prompt_tokens=50, completion_tokens=10,
    )

    tool = AiTool(
        name="ping",
        description="ping",
        parameters={},
        handler=lambda: '"pong"',
    )

    with mock.patch.object(
        client._client.chat.completions,
        "create",
        side_effect=[round_one, round_two],
    ):
        result = client.send_message_with_tools("hi", tools=[tool])

    assert result == "done"
    usage = client.get_last_usage()
    assert usage is not None
    assert usage.prompt_tokens == 150
    assert usage.completion_tokens == 30
    assert usage.total_tokens == 180


def test_unknown_model_falls_back_to_default_pricing() -> None:
    """An unknown model should still produce a non-zero cost estimate."""
    client = OpenAiClient("test-key", model="some-unreleased-model-2027")
    fake = _stop_response_with_usage(
        content="x", prompt_tokens=1000, completion_tokens=1000,
    )
    with mock.patch.object(
        client._client.chat.completions, "create", return_value=fake,
    ):
        client.send_message("p")

    usage = client.get_last_usage()
    assert usage is not None
    assert usage.estimated_cost_usd > 0


# ---------------------------------------------------------------------------
# Resilience: tenacity retry around OpenAI calls (extra credit)
# ---------------------------------------------------------------------------


def _connection_error() -> Exception:
    """Build a real APIConnectionError without invoking its constructor twice."""
    from openai import APIConnectionError

    return APIConnectionError(request=mock.MagicMock())


def test_openai_call_retries_then_succeeds() -> None:
    """Two transient APIConnectionErrors should be retried; the third call wins."""
    client = OpenAiClient("test-key")
    success = _stop_response_with_usage(
        content="ok", prompt_tokens=1, completion_tokens=1,
    )
    fake_create = mock.Mock(
        side_effect=[
            _connection_error(),
            _connection_error(),
            success,
        ],
    )
    with mock.patch.object(
        client._client.chat.completions, "create", fake_create,
    ):
        result = client.send_message("hi")

    assert result == "ok"
    assert fake_create.call_count == 3


def test_openai_call_gives_up_after_max_attempts() -> None:
    """After the configured max attempts, the underlying error reraises."""
    from openai import APIConnectionError

    client = OpenAiClient("test-key")
    fake_create = mock.Mock(
        side_effect=[_connection_error(), _connection_error(), _connection_error()],
    )
    with (
        mock.patch.object(client._client.chat.completions, "create", fake_create),
        pytest.raises(APIConnectionError),
    ):
        client.send_message("hi")
    assert fake_create.call_count == 3


def test_non_retryable_error_is_not_retried() -> None:
    """Non-transient exceptions (e.g. ValueError) should fail on first attempt."""
    client = OpenAiClient("test-key")
    fake_create = mock.Mock(side_effect=ValueError("bad input"))
    with (
        mock.patch.object(client._client.chat.completions, "create", fake_create),
        pytest.raises(ValueError, match="bad input"),
    ):
        client.send_message("hi")
    assert fake_create.call_count == 1
