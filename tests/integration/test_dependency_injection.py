"""Integration tests for dependency injection."""

import os
import sys
from unittest import mock

import pytest
from chat_client_api.client import (
    Channel,
    ChatClient,
    Message,
    _ClientRegistry,
    get_client,
    register_client,
)


def _reset_registry() -> None:
    """Reset the client registry to a clean state between tests."""
    _ClientRegistry._factory = None


def test_slack_client_registration() -> None:
    """Test that importing slack_client_impl registers it."""
    if "slack_client_impl" in sys.modules:
        del sys.modules["slack_client_impl"]
    if "slack_client_impl.client" in sys.modules:
        del sys.modules["slack_client_impl.client"]

    _reset_registry()

    with mock.patch.dict(os.environ, {"SLACK_BOT_TOKEN": "test-token"}):
        import slack_client_impl  # noqa: F401

        client = get_client()
        assert isinstance(client, ChatClient)
        assert client.__class__.__name__ == "SlackClient"


def test_no_client_registered_raises_runtime_error() -> None:
    """get_client should raise RuntimeError when no factory is registered."""
    _reset_registry()

    with pytest.raises(RuntimeError, match="No chat client implementation registered"):
        get_client()


def test_register_client_replaces_previous_factory() -> None:
    """Registering a second factory replaces the first."""
    call_count = {"n": 0}

    class DummyClient(ChatClient):
        def send_message(self, channel_id: str, text: str) -> Message:
            return Message(
                message_id=f"{channel_id}:0",
                channel=channel_id,
                text=text,
                sender="",
                timestamp="0",
            )

        def get_channels(self) -> list[Channel]:
            return []

        def get_channel(self, channel_id: str) -> Channel:
            return Channel(channel_id=channel_id, name="", is_private=False)

        def get_messages(
            self,
            channel_id: str,
            limit: int = 10,
            cursor: str | None = None,
        ) -> list[Message]:
            return []

        def get_message(self, message_id: str) -> Message:
            return Message(
                message_id=message_id, channel="", text="", sender="", timestamp="",
            )

        def delete_message(self, message_id: str) -> None:
            pass

    def factory_a() -> ChatClient:
        call_count["n"] += 1
        return DummyClient()

    def factory_b() -> ChatClient:
        return DummyClient()

    _reset_registry()
    register_client(factory_a)
    register_client(factory_b)

    # factory_b is now active; factory_a should never be called
    result = get_client()
    assert isinstance(result, ChatClient)
    assert call_count["n"] == 0
