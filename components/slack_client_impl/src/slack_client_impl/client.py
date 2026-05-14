"""Slack implementation of ChatClient."""
import os
from typing import Any

from chat_client_api.client import (
    Channel,
    ChatClient,
    Message,
    register_client,
)
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

_MESSAGE_ID_SEP = ":"


def _encode_message_id(channel: str, ts: str) -> str:
    return f"{channel}{_MESSAGE_ID_SEP}{ts}"


def _decode_message_id(message_id: str) -> tuple[str, str]:
    parts = message_id.split(_MESSAGE_ID_SEP, 1)
    if len(parts) != 2:  # noqa: PLR2004
        msg = (
            f"Invalid message_id format: {message_id!r}. "
            "Expected 'channel_id:timestamp'."
        )
        raise ValueError(msg)
    return parts[0], parts[1]


class SlackClient(ChatClient):
    """Slack implementation of the ChatClient interface."""

    def __init__(self, token: str) -> None:
        """Initialize Slack client.

        Args:
            token: Slack bot token

        """
        self.token = token
        self.client = WebClient(token=token)

    def send_message(
        self,
        channel_id: str,
        text: str,
    ) -> Message:
        """Send a message to a Slack channel.

        Args:
            channel_id: Channel ID or name
            text: Message text to send

        Returns:
            The sent Message object

        Raises:
            ValueError: If the message could not be sent

        """
        try:
            response = self.client.chat_postMessage(
                channel=channel_id,
                text=text,
            )
        except SlackApiError as exc:
            error = exc.response.get("error", "unknown") if exc.response else "unknown"
            msg = f"Failed to send message to {channel_id}: {error}"
            raise ValueError(msg) from exc

        if not response.get("ok"):
            error = response.get("error", "unknown_error")
            msg = f"Slack API error sending to {channel_id}: {error}"
            raise ValueError(msg)

        ts = str(response.get("ts", ""))
        ch = str(response.get("channel", channel_id))
        if not ts:
            msg = f"Slack returned ok but no timestamp for {channel_id}"
            raise ValueError(msg)

        return Message(
            message_id=_encode_message_id(ch, ts),
            channel=ch,
            text=text,
            sender="",
            timestamp=ts,
        )

    def get_channels(self) -> list[Channel]:
        """List all Slack channels.

        Returns:
            List of Channel objects

        """
        try:
            response = self.client.conversations_list()
            return [
                Channel(
                    channel_id=str(ch["id"]),
                    name=str(ch["name"]),
                    is_private=bool(ch["is_private"]),
                )
                for ch in response["channels"]
            ]
        except SlackApiError:
            return []

    def get_channel(self, channel_id: str) -> Channel:
        """Get a single Slack channel by ID.

        Args:
            channel_id: The Slack channel ID

        Returns:
            Channel object

        Raises:
            ValueError: If channel is not found or API call fails

        """
        try:
            response = self.client.conversations_info(channel=channel_id)
            ch = response["channel"]
            return Channel(
                channel_id=str(ch["id"]),
                name=str(ch["name"]),
                is_private=bool(ch["is_private"]),
            )
        except SlackApiError as exc:
            msg = f"Channel not found: {channel_id}"
            raise ValueError(msg) from exc

    def get_messages(
        self,
        channel_id: str,
        limit: int = 10,
        cursor: str | None = None,
    ) -> list[Message]:
        """Get recent messages from a Slack channel.

        Args:
            channel_id: Channel ID or name
            limit: Maximum number of messages
            cursor: Pagination cursor

        Returns:
            List of Message objects

        """
        try:
            if cursor:
                response = self.client.conversations_history(
                    channel=channel_id,
                    limit=limit,
                    cursor=cursor,
                )
            else:
                response = self.client.conversations_history(
                    channel=channel_id,
                    limit=limit,
                )
            return [
                Message(
                    message_id=_encode_message_id(channel_id, str(msg.get("ts", ""))),
                    channel=channel_id,
                    text=str(msg.get("text", "")),
                    sender=str(msg.get("user", "unknown")),
                    timestamp=str(msg.get("ts", "")),
                )
                for msg in response["messages"]
            ]
        except SlackApiError:
            return []

    def get_message(self, message_id: str) -> Message:
        """Get a single Slack message by encoded ID.

        Args:
            message_id: Encoded message ID in format 'channel_id:timestamp'

        Returns:
            Message object

        Raises:
            ValueError: If message is not found

        """
        channel, ts = _decode_message_id(message_id)
        try:
            response = self.client.conversations_history(
                channel=channel,
                latest=ts,
                oldest=ts,
                limit=1,
                inclusive=True,
            )
            messages: list[Any] = response.get("messages", [])
            if not messages:
                msg = f"Message not found: {message_id}"
                raise ValueError(msg)
            raw = messages[0]
            return Message(
                message_id=message_id,
                channel=channel,
                text=str(raw.get("text", "")),
                sender=str(raw.get("user", "unknown")),
                timestamp=ts,
            )
        except SlackApiError as exc:
            msg = f"Message not found: {message_id}"
            raise ValueError(msg) from exc

    def delete_message(self, message_id: str) -> None:
        """Delete a Slack message by encoded ID.

        Args:
            message_id: Encoded message ID in format 'channel_id:timestamp'

        Raises:
            ValueError: If message cannot be deleted

        """
        channel, ts = _decode_message_id(message_id)
        try:
            self.client.chat_delete(channel=channel, ts=ts)
        except SlackApiError as exc:
            msg = f"Failed to delete message: {message_id}"
            raise ValueError(msg) from exc


def _create_slack_client() -> SlackClient:
    """Create Slack client from environment variables.

    Returns:
        SlackClient instance

    Raises:
        ValueError: If token not set

    """
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        msg = "SLACK_BOT_TOKEN environment variable must be set"
        raise ValueError(msg)
    return SlackClient(token)


# Register this implementation when module is imported
register_client(_create_slack_client)
