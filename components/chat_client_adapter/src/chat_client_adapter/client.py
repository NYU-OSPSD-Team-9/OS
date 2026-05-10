"""Adapter implementing the ChatClient interface over the remote service."""

from __future__ import annotations

import os
import time
import webbrowser
from dataclasses import dataclass
from typing import Protocol, TypeVar

import httpx
from chat_client_api.client import (
    Channel,
    ChatClient,
    Message,
    register_client,
)
from chat_client_service_api_client.api.default import (
    create_auth_session_auth_sessions_post as create_auth_session_api,
)
from chat_client_service_api_client.api.default import (
    delete_auth_session_auth_sessions_session_id_delete as delete_auth_session_api,
)
from chat_client_service_api_client.api.default import (
    get_auth_session_auth_sessions_session_id_get as get_auth_session_api,
)
from chat_client_service_api_client.api.default import (
    get_messages_messages_get as get_messages_api,
)
from chat_client_service_api_client.api.default import (
    list_channels_channels_get as list_channels_api,
)
from chat_client_service_api_client.api.default import (
    send_message_messages_post as send_message_api,
)
from chat_client_service_api_client.client import Client as GeneratedClient
from chat_client_service_api_client.models.http_validation_error import (
    HTTPValidationError,
)
from chat_client_service_api_client.models.send_message_request import (
    SendMessageRequest,
)

ResponseT = TypeVar("ResponseT")


class ChatClientAdapterError(RuntimeError):
    """Base error for adapter failures."""


class ChatClientAuthenticationTimeoutError(ChatClientAdapterError):
    """Raised when OAuth does not complete within the configured timeout."""


@dataclass(frozen=True)
class ServiceAuthSession:
    """Represents a pending or completed service auth session."""

    session_id: str
    login_url: str
    status_url: str


@dataclass(frozen=True)
class ServiceAuthStatus:
    """Represents the current state of a service auth session."""

    session_id: str
    authenticated: bool
    team_name: str | None = None


@dataclass(frozen=True)
class AdapterAuthConfig:
    """Controls how the adapter completes remote OAuth."""

    open_browser: bool = True
    auth_timeout_seconds: float = 300.0
    poll_interval_seconds: float = 2.0


class ServiceGateway(Protocol):
    """Minimal gateway interface the adapter needs from the service client."""

    def create_auth_session(self) -> ServiceAuthSession:
        """Create a new pending auth session."""

    def get_auth_session_status(self, session_id: str) -> ServiceAuthStatus:
        """Fetch the current auth status for a session."""

    def delete_auth_session(self, session_id: str) -> None:
        """Delete an auth session."""

    def get_channels(self, session_id: str) -> list[Channel]:
        """List channels for the authenticated service session."""

    def get_channel(self, session_id: str, channel_id: str) -> Channel:
        """Get a single channel for the authenticated service session."""

    def send_message(
        self,
        session_id: str,
        channel: str,
        text: str,
    ) -> Message:
        """Send a message through the authenticated service session."""

    def get_messages(
        self,
        session_id: str,
        channel: str,
        limit: int = 10,
        cursor: str | None = None,
    ) -> list[Message]:
        """Fetch messages through the authenticated service session."""

    def get_message(self, session_id: str, message_id: str) -> Message:
        """Fetch a single message through the authenticated service session."""

    def delete_message(self, session_id: str, message_id: str) -> None:
        """Delete a message through the authenticated service session."""


class OpenAPIServiceGateway:
    """Thin gateway wrapping the generated OpenAPI client."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 20.0,
        client: GeneratedClient | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        """Initialize the gateway around the generated OpenAPI client."""
        normalized_base_url = base_url.rstrip("/")
        self._client = client or GeneratedClient(
            base_url=normalized_base_url,
            follow_redirects=False,
            raise_on_unexpected_status=True,
            timeout=httpx.Timeout(timeout_seconds),
        )
        self._base_url = normalized_base_url
        self._http_client = http_client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
        )

    def create_auth_session(self) -> ServiceAuthSession:
        """Create a new auth session on the remote service."""
        response = self._expect_result(
            create_auth_session_api.sync(client=self._client),
        )
        return ServiceAuthSession(
            session_id=response.session_id,
            login_url=response.login_url,
            status_url=response.status_url,
        )

    def get_auth_session_status(self, session_id: str) -> ServiceAuthStatus:
        """Fetch the current auth-session status."""
        response = self._expect_result(
            get_auth_session_api.sync(session_id=session_id, client=self._client),
        )
        team_name = response.team_name if isinstance(response.team_name, str) else None
        return ServiceAuthStatus(
            session_id=response.session_id,
            authenticated=response.authenticated,
            team_name=team_name,
        )

    def delete_auth_session(self, session_id: str) -> None:
        """Delete a remote auth session."""
        self._expect_result(
            delete_auth_session_api.sync(session_id=session_id, client=self._client),
        )

    def get_channels(self, session_id: str) -> list[Channel]:
        """List channels using the generated client."""
        response = self._expect_result(
            list_channels_api.sync(client=self._client, x_session_id=session_id),
        )
        return [
            Channel(
                channel_id=channel.channel_id,
                name=channel.name,
                is_private=channel.is_private,
            )
            for channel in response.channels
        ]

    def get_channel(self, session_id: str, channel_id: str) -> Channel:
        """Get a single channel via direct HTTP call."""
        response = self._http_client.get(
            f"{self._base_url}/channels/{channel_id}",
            headers={"X-Session-ID": session_id},
        )
        if response.status_code == 404:  # noqa: PLR2004
            msg = f"Channel not found: {channel_id}"
            raise ChatClientAdapterError(msg)
        response.raise_for_status()
        data = response.json()
        return Channel(
            channel_id=str(data["channel_id"]),
            name=str(data["name"]),
            is_private=bool(data["is_private"]),
        )

    def send_message(
        self,
        session_id: str,
        channel: str,
        text: str,
    ) -> Message:
        """Send a message using the generated client."""
        response = self._expect_result(
            send_message_api.sync(
                client=self._client,
                body=SendMessageRequest(channel=channel, text=text),
                x_session_id=session_id,
            ),
        )
        return Message(
            message_id=response.message_id,
            channel=response.channel,
            text=text,
            sender="",
            timestamp=response.timestamp,
        )

    def get_messages(
        self,
        session_id: str,
        channel: str,
        limit: int = 10,
        cursor: str | None = None,
    ) -> list[Message]:
        """Get messages using the generated client."""
        response = self._expect_result(
            get_messages_api.sync(
                client=self._client,
                channel=channel,
                limit=limit,
                cursor=cursor,
                x_session_id=session_id,
            ),
        )
        return [
            Message(
                message_id=message.message_id,
                channel=message.channel,
                text=message.text,
                sender=message.sender,
                timestamp=message.timestamp,
            )
            for message in response.messages
        ]

    def get_message(self, session_id: str, message_id: str) -> Message:
        """Get a single message via direct HTTP call."""
        response = self._http_client.get(
            f"{self._base_url}/messages/{message_id}",
            headers={"X-Session-ID": session_id},
        )
        if response.status_code == 404:  # noqa: PLR2004
            msg = f"Message not found: {message_id}"
            raise ChatClientAdapterError(msg)
        response.raise_for_status()
        data = response.json()
        return Message(
            message_id=str(data["message_id"]),
            channel=str(data["channel"]),
            text=str(data["text"]),
            sender=str(data["sender"]),
            timestamp=str(data["timestamp"]),
        )

    def delete_message(self, session_id: str, message_id: str) -> None:
        """Delete a message via direct HTTP call."""
        response = self._http_client.delete(
            f"{self._base_url}/messages/{message_id}",
            headers={"X-Session-ID": session_id},
        )
        if response.status_code == 404:  # noqa: PLR2004
            msg = f"Message not found: {message_id}"
            raise ChatClientAdapterError(msg)
        response.raise_for_status()

    def _expect_result(
        self,
        response: ResponseT | HTTPValidationError | None,
    ) -> ResponseT:
        if response is None:
            msg = "The chat client service returned an empty response."
            raise ChatClientAdapterError(msg)
        if isinstance(response, HTTPValidationError):
            msg = f"The chat client service rejected the request: {response.to_dict()}"
            raise ChatClientAdapterError(msg)
        return response


class ChatClientServiceAdapter(ChatClient):
    """Adapter that exposes the remote service through the ChatClient ABC."""

    def __init__(
        self,
        base_url: str,
        session_id: str | None = None,
        *,
        gateway: ServiceGateway | None = None,
        auth_config: AdapterAuthConfig | None = None,
    ) -> None:
        """Initialize the adapter with a base URL and optional session state."""
        self.base_url = base_url.rstrip("/")
        self.session_id = session_id
        self.gateway = gateway or OpenAPIServiceGateway(self.base_url)
        self.auth_config = auth_config or AdapterAuthConfig()

    def begin_authentication(self) -> ServiceAuthSession:
        """Create a new remote auth session and store its session ID locally."""
        auth_session = self.gateway.create_auth_session()
        self.session_id = auth_session.session_id
        return auth_session

    def wait_for_authentication(self) -> str:
        """Poll the service until the current session becomes authenticated."""
        session_id = self._require_session_id()
        deadline = time.monotonic() + self.auth_config.auth_timeout_seconds

        while time.monotonic() < deadline:
            status_response = self.gateway.get_auth_session_status(session_id)
            if status_response.authenticated:
                os.environ["CHAT_CLIENT_SERVICE_SESSION_ID"] = session_id
                return session_id
            time.sleep(self.auth_config.poll_interval_seconds)

        msg = (
            "OAuth authentication did not complete before the timeout expired. "
            "Open the login URL again and retry."
        )
        raise ChatClientAuthenticationTimeoutError(msg)

    def authenticate(self) -> str:
        """Start the OAuth flow and wait for completion."""
        auth_session = self.begin_authentication()
        if self.auth_config.open_browser:
            webbrowser.open(auth_session.login_url)
        return self.wait_for_authentication()

    def logout(self) -> None:
        """Delete the current remote auth session, if one exists."""
        if self.session_id is None:
            return
        self.gateway.delete_auth_session(self.session_id)
        self.session_id = None
        os.environ.pop("CHAT_CLIENT_SERVICE_SESSION_ID", None)

    def send_message(self, channel_id: str, text: str) -> Message:
        """Send a message via the remote chat client service."""
        session_id = self._ensure_authenticated_session_id()
        return self.gateway.send_message(
            session_id=session_id,
            channel=channel_id,
            text=text,
        )

    def get_channels(self) -> list[Channel]:
        """List channels via the remote chat client service."""
        session_id = self._ensure_authenticated_session_id()
        return self.gateway.get_channels(session_id=session_id)

    def get_channel(self, channel_id: str) -> Channel:
        """Get a single channel via the remote chat client service."""
        session_id = self._ensure_authenticated_session_id()
        try:
            return self.gateway.get_channel(
                session_id=session_id, channel_id=channel_id,
            )
        except ChatClientAdapterError as exc:
            msg = f"Channel not found: {channel_id}"
            raise ValueError(msg) from exc

    def get_messages(
        self,
        channel: str,
        limit: int = 10,
        cursor: str | None = None,
    ) -> list[Message]:
        """Get messages via the remote chat client service."""
        session_id = self._ensure_authenticated_session_id()
        return self.gateway.get_messages(
            session_id=session_id,
            channel=channel,
            limit=limit,
            cursor=cursor,
        )

    def get_message(self, message_id: str) -> Message:
        """Get a single message via the remote chat client service."""
        session_id = self._ensure_authenticated_session_id()
        try:
            return self.gateway.get_message(
                session_id=session_id, message_id=message_id,
            )
        except ChatClientAdapterError as exc:
            msg = f"Message not found: {message_id}"
            raise ValueError(msg) from exc

    def delete_message(self, message_id: str) -> None:
        """Delete a message via the remote chat client service."""
        session_id = self._ensure_authenticated_session_id()
        try:
            self.gateway.delete_message(session_id=session_id, message_id=message_id)
        except ChatClientAdapterError as exc:
            msg = f"Failed to delete message: {message_id}"
            raise ValueError(msg) from exc

    def _ensure_authenticated_session_id(self) -> str:
        if self.session_id is None:
            self.authenticate()
        return self._require_session_id()

    def _require_session_id(self) -> str:
        if self.session_id is None:
            msg = (
                "No service session is available. Set CHAT_CLIENT_SERVICE_SESSION_ID "
                "or complete the OAuth flow first."
            )
            raise ChatClientAdapterError(msg)
        return self.session_id


def _parse_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError as exc:
        msg = f"{name} must be a valid number."
        raise ValueError(msg) from exc


def _parse_bool_env(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    msg = f"{name} must be a boolean-like value."
    raise ValueError(msg)


def _create_service_adapter() -> ChatClientServiceAdapter:
    """Create a service adapter from environment variables."""
    base_url = os.getenv("CHAT_CLIENT_SERVICE_BASE_URL")
    if base_url is None or not base_url.strip():
        msg = "CHAT_CLIENT_SERVICE_BASE_URL environment variable must be set"
        raise ValueError(msg)

    auth_config = AdapterAuthConfig(
        open_browser=_parse_bool_env(
            "CHAT_CLIENT_SERVICE_OPEN_BROWSER",
            default=True,
        ),
        auth_timeout_seconds=_parse_float_env(
            "CHAT_CLIENT_SERVICE_AUTH_TIMEOUT_SECONDS",
            300.0,
        ),
        poll_interval_seconds=_parse_float_env(
            "CHAT_CLIENT_SERVICE_POLL_INTERVAL_SECONDS",
            2.0,
        ),
    )
    return ChatClientServiceAdapter(
        base_url=base_url,
        session_id=os.getenv("CHAT_CLIENT_SERVICE_SESSION_ID"),
        auth_config=auth_config,
    )


register_client(_create_service_adapter)
