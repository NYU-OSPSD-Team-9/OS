"""Unit tests for Slack client implementation."""
import os
from typing import Any
from unittest import mock

import pytest
from slack_client_impl.client import (
    SlackClient,
    _create_slack_client,
    _decode_message_id,
    _encode_message_id,
)


def test_slack_client_initialization() -> None:
    """Test that SlackClient initializes with a token."""
    token = "xoxb-test-token"
    client = SlackClient(token)
    assert client.token == token


# ---------------------------------------------------------------------------
# message_id encoding helpers
# ---------------------------------------------------------------------------


def test_encode_message_id() -> None:
    """Encoded message ID should be channel:ts."""
    assert _encode_message_id("C001", "12345.678") == "C001:12345.678"


def test_decode_message_id() -> None:
    """Decoding should split on the first colon only."""
    channel, ts = _decode_message_id("C001:12345.678")
    assert channel == "C001"
    assert ts == "12345.678"


def test_decode_message_id_invalid_format() -> None:
    """Decoding an ID without a colon should raise ValueError."""
    with pytest.raises(ValueError, match="Invalid message_id format"):
        _decode_message_id("nocolon")


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------


def test_send_message_success() -> None:
    """Test send_message returns Message on success."""
    client = SlackClient("test-token")
    mock_response: dict[str, Any] = {
        "ok": True,
        "ts": "12345.678",
        "channel": "C001",
    }
    with mock.patch.object(
        client.client,
        "chat_postMessage",
        return_value=mock_response,
    ):
        result = client.send_message("C001", "Hello")
        assert result.channel == "C001"
        assert result.timestamp == "12345.678"
        assert result.message_id == "C001:12345.678"


def test_send_message_failure() -> None:
    """Test send_message raises ValueError on SlackApiError."""
    from slack_sdk.errors import SlackApiError
    client = SlackClient("test-token")
    with mock.patch.object(
        client.client,
        "chat_postMessage",
        side_effect=SlackApiError("error", {}),  # type: ignore[no-untyped-call]
    ):
        with pytest.raises(ValueError, match="Failed to send message"):
            client.send_message("general", "Hello")


# ---------------------------------------------------------------------------
# get_channels
# ---------------------------------------------------------------------------


def test_get_channels_success() -> None:
    """Test get_channels returns list of channels."""
    client = SlackClient("test-token")
    mock_response: dict[str, Any] = {
        "channels": [
            {
                "id": "C001",
                "name": "general",
                "is_private": False,
            },
        ],
    }
    with mock.patch.object(
        client.client,
        "conversations_list",
        return_value=mock_response,
    ):
        channels = client.get_channels()
        assert len(channels) == 1
        assert channels[0].name == "general"
        assert channels[0].channel_id == "C001"


def test_get_channels_failure() -> None:
    """Test get_channels returns empty list on error."""
    from slack_sdk.errors import SlackApiError
    client = SlackClient("test-token")
    with mock.patch.object(
        client.client,
        "conversations_list",
        side_effect=SlackApiError("error", {}),  # type: ignore[no-untyped-call]
    ):
        channels = client.get_channels()
        assert channels == []


# ---------------------------------------------------------------------------
# get_channel
# ---------------------------------------------------------------------------


def test_get_channel_success() -> None:
    """Test get_channel returns a single Channel."""
    client = SlackClient("test-token")
    mock_response: dict[str, Any] = {
        "channel": {
            "id": "C001",
            "name": "general",
            "is_private": False,
        },
    }
    with mock.patch.object(
        client.client,
        "conversations_info",
        return_value=mock_response,
    ):
        channel = client.get_channel("C001")
        assert channel.channel_id == "C001"
        assert channel.name == "general"


def test_get_channel_not_found() -> None:
    """Test get_channel raises ValueError when Slack returns an error."""
    from slack_sdk.errors import SlackApiError
    client = SlackClient("test-token")
    with mock.patch.object(
        client.client,
        "conversations_info",
        side_effect=SlackApiError("channel_not_found", {}),  # type: ignore[no-untyped-call]
    ):
        with pytest.raises(ValueError, match="Channel not found"):
            client.get_channel("C999")


# ---------------------------------------------------------------------------
# get_messages
# ---------------------------------------------------------------------------


def test_get_messages_success() -> None:
    """Test get_messages returns list of messages with encoded IDs."""
    client = SlackClient("test-token")
    mock_response: dict[str, Any] = {
        "messages": [
            {
                "ts": "12345.678",
                "text": "Hello",
                "user": "U001",
            },
        ],
    }
    with mock.patch.object(
        client.client,
        "conversations_history",
        return_value=mock_response,
    ):
        messages = client.get_messages("C001", limit=10)
        assert len(messages) == 1
        assert messages[0].text == "Hello"
        assert messages[0].sender == "U001"
        assert messages[0].message_id == "C001:12345.678"


def test_get_messages_with_cursor() -> None:
    """Test get_messages with pagination cursor."""
    client = SlackClient("test-token")
    mock_response: dict[str, Any] = {
        "messages": [],
    }
    with mock.patch.object(
        client.client,
        "conversations_history",
        return_value=mock_response,
    ) as mock_history:
        client.get_messages("C001", limit=10, cursor="abc123")
        mock_history.assert_called_once()


def test_get_messages_failure() -> None:
    """Test get_messages returns empty list on error."""
    from slack_sdk.errors import SlackApiError
    client = SlackClient("test-token")
    with mock.patch.object(
        client.client,
        "conversations_history",
        side_effect=SlackApiError("error", {}),  # type: ignore[no-untyped-call]
    ):
        messages = client.get_messages("C001")
        assert messages == []


# ---------------------------------------------------------------------------
# get_message
# ---------------------------------------------------------------------------


def test_get_message_success() -> None:
    """Test get_message fetches and returns a single Message."""
    client = SlackClient("test-token")
    mock_response: dict[str, Any] = {
        "messages": [
            {
                "ts": "12345.678",
                "text": "Hello",
                "user": "U001",
            },
        ],
    }
    with mock.patch.object(
        client.client,
        "conversations_history",
        return_value=mock_response,
    ):
        msg = client.get_message("C001:12345.678")
        assert msg.text == "Hello"
        assert msg.channel == "C001"
        assert msg.message_id == "C001:12345.678"


def test_get_message_not_found() -> None:
    """Test get_message raises ValueError when no messages returned."""
    client = SlackClient("test-token")
    with mock.patch.object(
        client.client,
        "conversations_history",
        return_value={"messages": []},
    ):
        with pytest.raises(ValueError, match="Message not found"):
            client.get_message("C001:12345.678")


def test_get_message_slack_error() -> None:
    """Test get_message raises ValueError on SlackApiError."""
    from slack_sdk.errors import SlackApiError
    client = SlackClient("test-token")
    with mock.patch.object(
        client.client,
        "conversations_history",
        side_effect=SlackApiError("error", {}),  # type: ignore[no-untyped-call]
    ):
        with pytest.raises(ValueError, match="Message not found"):
            client.get_message("C001:12345.678")


def test_get_message_invalid_id() -> None:
    """Test get_message raises ValueError for malformed message IDs."""
    client = SlackClient("test-token")
    with pytest.raises(ValueError, match="Invalid message_id format"):
        client.get_message("bad-id-no-colon")


# ---------------------------------------------------------------------------
# delete_message
# ---------------------------------------------------------------------------


def test_delete_message_success() -> None:
    """Test delete_message calls chat_delete with correct args."""
    client = SlackClient("test-token")
    with mock.patch.object(client.client, "chat_delete") as mock_delete:
        client.delete_message("C001:12345.678")
        mock_delete.assert_called_once_with(channel="C001", ts="12345.678")


def test_delete_message_failure() -> None:
    """Test delete_message raises ValueError on SlackApiError."""
    from slack_sdk.errors import SlackApiError
    client = SlackClient("test-token")
    with mock.patch.object(
        client.client,
        "chat_delete",
        side_effect=SlackApiError("cant_delete_message", {}),  # type: ignore[no-untyped-call]
    ):
        with pytest.raises(ValueError, match="Failed to delete message"):
            client.delete_message("C001:12345.678")


def test_delete_message_invalid_id() -> None:
    """Test delete_message raises ValueError for malformed IDs."""
    client = SlackClient("test-token")
    with pytest.raises(ValueError, match="Invalid message_id format"):
        client.delete_message("nocolon")


# ---------------------------------------------------------------------------
# Factory & registration
# ---------------------------------------------------------------------------


def test_create_slack_client_with_token() -> None:
    """Test factory function creates client when token is set."""
    with mock.patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-test"}):
        client = _create_slack_client()
        assert isinstance(client, SlackClient)
        assert client.token == "xoxb-test"


def test_create_slack_client_without_token() -> None:
    """Test factory function raises ValueError when token is missing."""
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(
            ValueError,
            match="SLACK_BOT_TOKEN environment variable must be set",
        ):
            _create_slack_client()


def test_slack_client_inherits_from_chat_client() -> None:
    """Test that SlackClient properly inherits from ChatClient."""
    from chat_client_api.client import ChatClient

    client = SlackClient("test-token")
    assert isinstance(client, ChatClient)
