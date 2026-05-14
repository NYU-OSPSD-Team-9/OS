"""Abstract interface for chat clients."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Message:
    """Represents a chat message."""

    message_id: str
    channel: str
    text: str
    sender: str
    timestamp: str


@dataclass
class Channel:
    """Represents a chat channel."""

    channel_id: str
    name: str
    is_private: bool | None = None
    channel_type: str | None = None


class ChatClient(ABC):
    """Abstract base class for chat client implementations."""

    @abstractmethod
    def send_message(self, channel_id: str, text: str) -> Message:
        """Send a message to a channel.

        Args:
            channel_id: Channel ID or name
            text: Message text to send

        Returns:
            The sent Message object

        Raises:
            ValueError: If the message could not be sent

        """

    @abstractmethod
    def get_channels(self) -> list[Channel]:
        """List all available channels.

        Returns:
            List of Channel objects

        """

    @abstractmethod
    def get_channel(self, channel_id: str) -> Channel:
        """Get a single channel by ID.

        Args:
            channel_id: The channel ID to retrieve

        Returns:
            Channel object

        Raises:
            ValueError: If channel is not found

        """

    @abstractmethod
    def get_messages(
        self,
        channel_id: str,
        limit: int = 10,
        cursor: str | None = None,
    ) -> list[Message]:
        """Get recent messages from a channel.

        Args:
            channel_id: Channel ID or name
            limit: Maximum number of messages to retrieve
            cursor: Optional pagination cursor. Implementations that do not
                support cursor-based pagination may ignore this parameter.

        Returns:
            List of Message objects

        """

    @abstractmethod
    def get_message(self, message_id: str) -> Message:
        """Get a single message by its opaque ID.

        Args:
            message_id: Opaque message identifier. Format is
                implementation-defined.

        Returns:
            Message object

        Raises:
            ValueError: If message is not found

        """

    @abstractmethod
    def delete_message(self, message_id: str) -> None:
        """Delete a message by its opaque ID.

        Args:
            message_id: Opaque message identifier. Format is
                implementation-defined.

        Raises:
            ValueError: If message cannot be deleted

        """


class _ClientRegistry:
    """Holds the registered client factory — avoids global mutation."""

    _factory: Callable[[], ChatClient] | None = None

    @classmethod
    def set(cls, factory: Callable[[], ChatClient]) -> None:
        """Register a factory.

        Args:
            factory: Callable that returns a ChatClient instance

        """
        cls._factory = factory

    @classmethod
    def get(cls) -> Callable[[], ChatClient] | None:
        """Get the registered factory.

        Returns:
            The registered factory or None

        """
        return cls._factory


def get_client() -> ChatClient:
    """Get the registered chat client implementation.

    Returns:
        Instance of registered ChatClient

    Raises:
        RuntimeError: If no implementation is registered

    """
    factory = _ClientRegistry.get()
    if factory is None:
        msg = (
            "No chat client implementation registered. "
            "Import an implementation package to register it."
        )
        raise RuntimeError(msg)
    return factory()


def register_client(factory: Callable[[], ChatClient]) -> None:
    """Register a chat client implementation factory.

    Args:
        factory: Callable that returns a ChatClient instance

    """
    _ClientRegistry.set(factory)
