"""Pydantic models, dataclasses, and session management for the chat client service."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from chat_client_api.client import Channel, Message
    from ticket_client_api.client import Ticket


@dataclass(frozen=True)
class ServiceSettings:
    """Runtime configuration for the chat client service."""

    service_base_url: str
    slack_client_id: str | None
    slack_client_secret: str | None
    slack_redirect_uri: str
    slack_scopes: str


@dataclass
class AuthSession:
    """Represents a single authenticated service session."""

    session_id: str
    slack_bot_token: str | None = None
    team_name: str | None = None


class InMemoryAuthSessionStore:
    """Stores OAuth session state in process memory."""

    def __init__(self) -> None:
        """Initialize empty session and state indexes."""
        self._sessions: dict[str, AuthSession] = {}
        self._oauth_state_to_session_id: dict[str, str] = {}

    def create_session(self) -> AuthSession:
        """Create and store a new pending auth session."""
        session_id = secrets.token_urlsafe(24)
        session = AuthSession(session_id=session_id)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> AuthSession | None:
        """Return a stored session if it exists."""
        return self._sessions.get(session_id)

    def require_session(self, session_id: str) -> AuthSession:
        """Return a stored session or raise HTTP 404."""
        session = self.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Unknown auth session.",
            )
        return session

    def require_authenticated_session(self, session_id: str) -> AuthSession:
        """Return an authenticated session or raise HTTP 401."""
        session = self.require_session(session_id)
        if not session.slack_bot_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session is not authenticated. Complete /auth/login first.",
            )
        return session

    def bind_state(self, session_id: str, state: str) -> None:
        """Associate an OAuth state token with an auth session."""
        self.require_session(session_id)
        self._oauth_state_to_session_id[state] = session_id

    def pop_session_for_state(self, state: str) -> AuthSession | None:
        """Resolve and remove a pending OAuth state token."""
        session_id = self._oauth_state_to_session_id.pop(state, None)
        if session_id is None:
            return None
        return self._sessions.get(session_id)

    def authenticate_session(
        self,
        session_id: str,
        slack_bot_token: str,
        team_name: str | None,
    ) -> AuthSession:
        """Store Slack credentials for an existing auth session."""
        session = self.require_session(session_id)
        session.slack_bot_token = slack_bot_token
        session.team_name = team_name
        return session

    def delete_session(self, session_id: str) -> None:
        """Delete an auth session and any pending OAuth state."""
        self._sessions.pop(session_id, None)
        states_to_remove = [
            state
            for state, bound_session_id in self._oauth_state_to_session_id.items()
            if bound_session_id == session_id
        ]
        for state in states_to_remove:
            self._oauth_state_to_session_id.pop(state, None)

    def reset(self) -> None:
        """Clear all stored sessions. Intended for tests."""
        self._sessions.clear()
        self._oauth_state_to_session_id.clear()


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str


class AuthSessionResponse(BaseModel):
    """Created auth session response model."""

    session_id: str
    authenticated: bool
    login_url: str
    status_url: str


class AuthSessionStatusResponse(BaseModel):
    """Auth session status response model."""

    session_id: str
    authenticated: bool
    team_name: str | None = None


class AuthCallbackResponse(BaseModel):
    """OAuth callback completion response model."""

    status: str
    message: str


class LogoutResponse(BaseModel):
    """Auth session deletion response model."""

    status: str


class ChannelModel(BaseModel):
    """Serialized channel response model."""

    channel_id: str
    name: str
    is_private: bool | None = None
    channel_type: str | None = None

    @classmethod
    def from_dto(cls, channel: Channel) -> ChannelModel:
        """Convert a channel DTO into an API response model."""
        return cls(
            channel_id=channel.channel_id,
            name=channel.name,
            is_private=channel.is_private,
            channel_type=channel.channel_type,
        )


class ListChannelsResponse(BaseModel):
    """List channels response model."""

    channels: list[ChannelModel]


class GetChannelResponse(BaseModel):
    """Get single channel response model."""

    channel_id: str
    name: str
    is_private: bool | None = None
    channel_type: str | None = None

    @classmethod
    def from_dto(cls, channel: Channel) -> GetChannelResponse:
        """Convert a channel DTO into an API response model."""
        return cls(
            channel_id=channel.channel_id,
            name=channel.name,
            is_private=channel.is_private,
            channel_type=channel.channel_type,
        )


class SendMessageRequest(BaseModel):
    """Send message request model."""

    channel: str = Field(min_length=1)
    text: str = Field(min_length=1)


class MessageModel(BaseModel):
    """Serialized chat message response model."""

    message_id: str
    channel: str
    text: str
    sender: str
    timestamp: str

    @classmethod
    def from_dto(cls, message: Message) -> MessageModel:
        """Convert a message DTO into an API response model."""
        return cls(
            message_id=message.message_id,
            channel=message.channel,
            text=message.text,
            sender=message.sender,
            timestamp=message.timestamp,
        )


class GetMessagesResponse(BaseModel):
    """Get messages response model."""

    messages: list[MessageModel]


class DeleteMessageResponse(BaseModel):
    """Delete message response model."""

    status: str


class RouteMetricsEntry(BaseModel):
    """Per-(route, method) breakdown of request volume and latency."""

    route: str
    method: str
    count: int
    ok_count: int
    domain_error_count: int
    infra_error_count: int
    average_latency_ms: float


class AiUsageMetrics(BaseModel):
    """Aggregate AI provider usage metrics."""

    calls_total: int = 0
    prompt_tokens_total: int = 0
    completion_tokens_total: int = 0
    total_tokens_total: int = 0
    estimated_cost_usd_total: float = 0.0


class MetricsSnapshot(BaseModel):
    """Current telemetry snapshot."""

    total_requests: int
    successful_requests: int
    failed_requests: int
    domain_error_count: int = 0
    infra_error_count: int = 0
    success_rate: float
    failure_rate: float
    average_latency_ms: float
    by_route: list[RouteMetricsEntry] = []
    ai_usage: AiUsageMetrics = AiUsageMetrics()


class AiChatRequest(BaseModel):
    """AI chat request model."""

    prompt: str = Field(min_length=1)
    channel: str | None = None


class AiChatResponse(BaseModel):
    """AI chat response model."""

    reply: str


class IssueModel(BaseModel):
    """Serialized issue from the Jira vertical."""

    issue_id: str
    title: str
    status: str
    description: str

    @classmethod
    def from_dto(cls, ticket: Ticket) -> IssueModel:
        """Convert a Ticket DTO to an API model."""
        return cls(
            issue_id=ticket.ticket_id,
            title=ticket.title,
            status=ticket.status,
            description=ticket.description,
        )


TicketModel = IssueModel


class ListIssuesResponse(BaseModel):
    """Response model for listing issues from the Jira vertical."""

    issues: list[IssueModel]


ListTicketsResponse = ListIssuesResponse


class GetIssueResponse(BaseModel):
    """Response model for fetching one issue."""

    issue: IssueModel


GetTicketResponse = GetIssueResponse


class CreateIssueRequest(BaseModel):
    """Request model for creating an issue."""

    title: str = Field(min_length=1)
    description: str = Field(min_length=1)


CreateTicketRequest = CreateIssueRequest


class CreateIssueResponse(BaseModel):
    """Response model for creating one issue."""

    issue: IssueModel


CreateTicketResponse = CreateIssueResponse


class UpdateIssueStatusRequest(BaseModel):
    """Request model for changing an issue status."""

    new_status: str = Field(min_length=1)


UpdateTicketStatusRequest = UpdateIssueStatusRequest


class UpdateIssueStatusResponse(BaseModel):
    """Response model for issue status updates."""

    status: str
    issue_id: str


UpdateTicketStatusResponse = UpdateIssueStatusResponse
