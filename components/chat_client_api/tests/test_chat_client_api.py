"""Unit tests for chat client API."""

import pytest
from chat_client_api.client import (
    Channel,
    ChatClient,
    Message,
    _ClientRegistry,
    get_client,
    register_client,
)


def setup_function() -> None:
    """Reset registry before each test."""
    _ClientRegistry._factory = None


class MockClient(ChatClient):
    """Mock client for testing."""

    def send_message(self, channel_id: str, text: str) -> Message:
        """Send a mock message."""
        return Message(
            message_id=f"{channel_id}:12345.678",
            channel=channel_id,
            text=text,
            sender="",
            timestamp="12345.678",
        )

    def get_channels(self) -> list[Channel]:
        """List mock channels."""
        return [
            Channel(channel_id="C123", name="general", is_private=False),
        ]

    def get_channel(self, channel_id: str) -> Channel:
        """Get a mock channel."""
        return Channel(channel_id=channel_id, name="general", is_private=False)

    def get_messages(
        self,
        channel_id: str,
        limit: int = 10,
        cursor: str | None = None,
    ) -> list[Message]:
        """Get mock messages."""
        return [
            Message(
                message_id=f"{channel_id}:12345.678",
                channel=channel_id,
                text="Hello",
                sender="U123",
                timestamp="12345.678",
            ),
        ]

    def get_message(self, message_id: str) -> Message:
        """Get a mock message."""
        parts = message_id.split(":", 1)
        channel = parts[0] if len(parts) == 2 else "C123"
        return Message(
            message_id=message_id,
            channel=channel,
            text="Hello",
            sender="U123",
            timestamp="12345.678",
        )

    def delete_message(self, message_id: str) -> None:
        """Delete a mock message (no-op)."""


def test_get_client_raises_when_no_implementation_registered() -> None:
    """Test that get_client raises RuntimeError when no implementation is registered."""
    with pytest.raises(RuntimeError, match="No chat client implementation registered"):
        get_client()


def test_register_client_stores_factory() -> None:
    """Test that register_client stores the factory function."""

    def mock_factory() -> ChatClient:
        """Create a mock client."""
        return MockClient()

    register_client(mock_factory)
    assert _ClientRegistry.get() is not None


def test_get_client_returns_registered_implementation() -> None:
    """Test that get_client returns the registered implementation."""
    register_client(MockClient)
    client = get_client()
    assert isinstance(client, MockClient)


def test_send_message_returns_correct_dto() -> None:
    """Test send_message returns a Message."""
    register_client(MockClient)
    client = get_client()
    result = client.send_message("general", "hello")
    assert isinstance(result, Message)
    assert result.channel == "general"
    assert result.text == "hello"


def test_get_channels_returns_channel_list() -> None:
    """Test get_channels returns a list of Channel DTOs."""
    register_client(MockClient)
    client = get_client()
    channels = client.get_channels()
    assert isinstance(channels[0], Channel)
    assert channels[0].name == "general"


def test_get_channel_returns_single_channel() -> None:
    """Test get_channel returns a single Channel DTO."""
    register_client(MockClient)
    client = get_client()
    channel = client.get_channel("C123")
    assert isinstance(channel, Channel)
    assert channel.channel_id == "C123"


def test_get_messages_returns_message_list() -> None:
    """Test get_messages returns a list of Message DTOs."""
    register_client(MockClient)
    client = get_client()
    messages = client.get_messages("general")
    assert isinstance(messages[0], Message)
    assert messages[0].text == "Hello"


def test_get_message_returns_single_message() -> None:
    """Test get_message returns a single Message DTO."""
    register_client(MockClient)
    client = get_client()
    message = client.get_message("C123:12345.678")
    assert isinstance(message, Message)
    assert message.message_id == "C123:12345.678"


def test_delete_message_does_not_raise() -> None:
    """Test delete_message completes without error on valid message."""
    register_client(MockClient)
    client = get_client()
    client.delete_message("C123:12345.678")  # should not raise
