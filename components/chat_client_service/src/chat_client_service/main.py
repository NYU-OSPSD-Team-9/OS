"""FastAPI service exposing the chat client contract over HTTP."""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
from ai_client_api.client import AiTool, TokenUsage, get_ai_client
from calendar_client_api import (
    Client as CalendarClient,
)
from calendar_client_api import (
    EventPatch as CalendarEventPatch,
)
from chat_client_api.client import ChatClient
from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import RedirectResponse
from work_mgmt_client_interface import (
    IssueTrackerClient,
)
from work_mgmt_client_interface import (
    IssueUpdate as DiamondsIssueUpdate,
)
from work_mgmt_client_interface import (
    Status as DiamondsStatus,
)

from .models import (
    AiChatRequest,
    AiChatResponse,
    AiUsageMetrics,
    AuthCallbackResponse,
    AuthSessionResponse,
    AuthSessionStatusResponse,
    ChannelModel,
    CreateIssueRequest,
    CreateIssueResponse,
    DeleteMessageResponse,
    GetChannelResponse,
    GetIssueResponse,
    GetMessagesResponse,
    HealthResponse,
    InMemoryAuthSessionStore,
    IssueModel,
    ListChannelsResponse,
    ListIssuesResponse,
    LogoutResponse,
    MessageModel,
    MetricsSnapshot,
    RouteMetricsEntry,
    SendMessageRequest,
    ServiceSettings,
    UpdateIssueStatusRequest,
    UpdateIssueStatusResponse,
)

IssueUpdate = None
IssueStatus = None
TokenClientFactory = Callable[[str], ChatClient]


def _default_client_factory(token: str) -> ChatClient:
    # Lazy import keeps the service decoupled from SlackClient at module load.
    from slack_client_impl.client import SlackClient

    return SlackClient(token)


_client_factory: TokenClientFactory = _default_client_factory

app = FastAPI(
    title="Chat Client Service",
    description="Slack-backed chat client service with OAuth session tokens.",
    version="0.3.0",
)

_session_store = InMemoryAuthSessionStore()
SessionHeader = Annotated[str | None, Header(alias="X-Session-ID")]

# ---------------------------------------------------------------------------
# Simple in-process telemetry counters
# ---------------------------------------------------------------------------


_metrics_lock = threading.Lock()
_metrics: dict[str, float] = {
    "total_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "domain_errors": 0,
    "infra_errors": 0,
    "total_latency_ms": 0,
}

_ai_metrics_lock = threading.Lock()
_ai_metrics: dict[str, float] = {
    "ai_calls_total": 0,
    "ai_prompt_tokens_total": 0,
    "ai_completion_tokens_total": 0,
    "ai_total_tokens_total": 0,
    "ai_estimated_cost_usd_total": 0.0,
}

_HTTP_CLIENT_ERROR_FLOOR = 400
_HTTP_SERVER_ERROR_FLOOR = 500

_labeled_counts: dict[tuple[str, str, str], int] = {}
_labeled_latency_sum: dict[tuple[str, str], float] = {}
_labeled_latency_count: dict[tuple[str, str], int] = {}


def _classify_status(status_code: int) -> str:
    """Map HTTP status code to ok / domain_error / infra_error."""
    if status_code < _HTTP_CLIENT_ERROR_FLOOR:
        return "ok"
    if status_code < _HTTP_SERVER_ERROR_FLOOR:
        return "domain_error"
    return "infra_error"


def _route_template(request: Request) -> str:
    """Return the matched FastAPI route template, or the literal path."""
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    if isinstance(template, str) and template:
        return template
    return request.url.path


@app.middleware("http")
async def _telemetry_middleware(
    request: Request, call_next: Callable[[Request], object],
) -> Response:
    """Track request count, latency, and labeled success/failure rate."""
    start = time.perf_counter()
    response: Response = await call_next(request)  # type: ignore[misc]
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    template = _route_template(request)
    method = request.method
    status_class = _classify_status(response.status_code)
    label_key = (template, method, status_class)
    latency_key = (template, method)

    with _metrics_lock:
        _metrics["total_requests"] += 1
        _metrics["total_latency_ms"] += elapsed_ms

        if status_class == "ok":
            _metrics["successful_requests"] += 1
        else:
            _metrics["failed_requests"] += 1
            if status_class == "domain_error":
                _metrics["domain_errors"] += 1
            else:
                _metrics["infra_errors"] += 1

        _labeled_counts[label_key] = _labeled_counts.get(label_key, 0) + 1
        _labeled_latency_sum[latency_key] = (
            _labeled_latency_sum.get(latency_key, 0.0) + elapsed_ms
        )
        _labeled_latency_count[latency_key] = (
            _labeled_latency_count.get(latency_key, 0) + 1
        )

    return response


def get_settings() -> ServiceSettings:
    """Load service settings from the environment."""
    base_url = os.getenv("CHAT_CLIENT_SERVICE_BASE_URL", "http://localhost:8000")
    normalized_base_url = base_url.rstrip("/")
    return ServiceSettings(
        service_base_url=normalized_base_url,
        slack_client_id=os.getenv("SLACK_CLIENT_ID"),
        slack_client_secret=os.getenv("SLACK_CLIENT_SECRET"),
        slack_redirect_uri=os.getenv(
            "SLACK_REDIRECT_URI",
            f"{normalized_base_url}/auth/callback",
        ),
        slack_scopes=os.getenv(
            "SLACK_SCOPES",
            "chat:write,channels:read,channels:history,chat:write.public",
        ),
    )


def build_chat_client(slack_bot_token: str) -> ChatClient:
    """Create a chat client for the given token using the registered factory."""
    return _client_factory(slack_bot_token)


def reset_service_state() -> None:
    """Reset global in-memory service state for tests."""
    _session_store.reset()
    for key in _metrics:
        _metrics[key] = 0
    _labeled_counts.clear()
    _labeled_latency_sum.clear()
    _labeled_latency_count.clear()
    for ai_key in _ai_metrics:
        _ai_metrics[ai_key] = 0


def _record_ai_usage(usage: TokenUsage | None) -> None:
    """Add a TokenUsage measurement to the aggregate AI counters.

    Called after every /ai/chat completion. Safe to pass ``None`` (skipped).
    """
    if usage is None:
        return
    with _ai_metrics_lock:
        _ai_metrics["ai_calls_total"] += 1
        _ai_metrics["ai_prompt_tokens_total"] += usage.prompt_tokens
        _ai_metrics["ai_completion_tokens_total"] += usage.completion_tokens
        _ai_metrics["ai_total_tokens_total"] += usage.total_tokens
        _ai_metrics["ai_estimated_cost_usd_total"] = round(
            _ai_metrics["ai_estimated_cost_usd_total"] + usage.estimated_cost_usd,
            6,
        )


def _build_login_url(settings: ServiceSettings, session_id: str) -> str:
    return f"{settings.service_base_url}/auth/login?session_id={session_id}"


def _build_status_url(settings: ServiceSettings, session_id: str) -> str:
    return f"{settings.service_base_url}/auth/sessions/{session_id}"


def _build_slack_authorization_url(
    settings: ServiceSettings,
    state: str,
) -> str:
    client_id = settings.slack_client_id
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SLACK_CLIENT_ID environment variable must be set.",
        )

    params = {
        "client_id": client_id,
        "scope": settings.slack_scopes,
        "redirect_uri": settings.slack_redirect_uri,
        "state": state,
    }
    return f"https://slack.com/oauth/v2/authorize?{urlencode(params)}"


def _exchange_slack_code_for_token(
    code: str,
    settings: ServiceSettings,
) -> dict[str, object]:
    if not settings.slack_client_id or not settings.slack_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SLACK_CLIENT_ID and SLACK_CLIENT_SECRET must be set.",
        )

    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "client_id": settings.slack_client_id,
                    "client_secret": settings.slack_client_secret,
                    "code": code,
                    "redirect_uri": settings.slack_redirect_uri,
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Slack token exchange request failed: {exc}",
        ) from exc

    payload = response.json()
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Slack returned an invalid token response.",
        )
    return payload


def _extract_team_name(payload: dict[str, object]) -> str | None:
    team_payload = payload.get("team")
    if not isinstance(team_payload, dict):
        return None

    name = team_payload.get("name")
    if isinstance(name, str) and name:
        return name
    return None


def _require_session_id(x_session_id: SessionHeader = None) -> str:
    if x_session_id is None or not x_session_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Session-ID header is required.",
        )
    return x_session_id


def _get_authenticated_client(
    session_id: Annotated[str, Depends(_require_session_id)],
) -> ChatClient:
    session = _session_store.require_authenticated_session(session_id)
    slack_bot_token = session.slack_bot_token
    if slack_bot_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is not authenticated.",
        )
    return build_chat_client(slack_bot_token)


def _build_metrics_snapshot() -> MetricsSnapshot:
    """Build a MetricsSnapshot from the in-process counters."""
    total = _metrics["total_requests"]
    success = _metrics["successful_requests"]
    failed = _metrics["failed_requests"]
    domain_errors = _metrics["domain_errors"]
    infra_errors = _metrics["infra_errors"]
    avg_latency = _metrics["total_latency_ms"] / total if total > 0 else 0.0

    by_route: list[RouteMetricsEntry] = []
    seen_routes: set[tuple[str, str]] = set()
    for (template, method) in _labeled_latency_count:
        seen_routes.add((template, method))
    for (template, method, _status_class) in _labeled_counts:
        seen_routes.add((template, method))
    for (template, method) in sorted(seen_routes):
        ok_count = _labeled_counts.get((template, method, "ok"), 0)
        domain_count = _labeled_counts.get((template, method, "domain_error"), 0)
        infra_count = _labeled_counts.get((template, method, "infra_error"), 0)
        latency_sum = _labeled_latency_sum.get((template, method), 0.0)
        latency_count = _labeled_latency_count.get((template, method), 0)
        avg = round(latency_sum / latency_count, 2) if latency_count > 0 else 0.0
        by_route.append(
            RouteMetricsEntry(
                route=template,
                method=method,
                count=ok_count + domain_count + infra_count,
                ok_count=ok_count,
                domain_error_count=domain_count,
                infra_error_count=infra_count,
                average_latency_ms=avg,
            ),
        )

    with _ai_metrics_lock:
        ai_usage = AiUsageMetrics(
            calls_total=int(_ai_metrics["ai_calls_total"]),
            prompt_tokens_total=int(_ai_metrics["ai_prompt_tokens_total"]),
            completion_tokens_total=int(_ai_metrics["ai_completion_tokens_total"]),
            total_tokens_total=int(_ai_metrics["ai_total_tokens_total"]),
            estimated_cost_usd_total=round(
                _ai_metrics["ai_estimated_cost_usd_total"], 6,
            ),
        )

    return MetricsSnapshot(
        total_requests=int(total),
        successful_requests=int(success),
        failed_requests=int(failed),
        domain_error_count=int(domain_errors),
        infra_error_count=int(infra_errors),
        success_rate=round(success / total, 4) if total > 0 else 0.0,
        failure_rate=round(failed / total, 4) if total > 0 else 0.0,
        average_latency_ms=round(avg_latency, 2),
        by_route=by_route,
        ai_usage=ai_usage,
    )


_diamonds_client_factory: Callable[[], IssueTrackerClient] | None = None


def register_diamonds_client_factory(
    factory: Callable[[], IssueTrackerClient] | None,
) -> None:
    """Register or clear the cross-vertical Diamonds IssueTrackerClient factory.

    Following the same get_client/register_client pattern as HW1, this lets
    consumers swap the Diamonds-backed implementation transparently.
    """
    global _diamonds_client_factory  # noqa: PLW0603
    _diamonds_client_factory = factory


def get_diamonds_client() -> IssueTrackerClient | None:
    """Return the registered Diamonds IssueTrackerClient, or None if unset."""
    if _diamonds_client_factory is None:
        return None
    return _diamonds_client_factory()


_DIAMONDS_TO_INTERNAL_STATUS: dict[DiamondsStatus, str] = {
    DiamondsStatus.TODO: "open",
    DiamondsStatus.IN_PROGRESS: "in_progress",
    DiamondsStatus.COMPLETE: "complete",
    DiamondsStatus.CANCELLED: "cancelled",
}

_INTERNAL_TO_DIAMONDS_STATUS: dict[str, DiamondsStatus] = {
    "open": DiamondsStatus.TODO,
    "todo": DiamondsStatus.TODO,
    "in_progress": DiamondsStatus.IN_PROGRESS,
    "in-progress": DiamondsStatus.IN_PROGRESS,
    "doing": DiamondsStatus.IN_PROGRESS,
    "complete": DiamondsStatus.COMPLETE,
    "completed": DiamondsStatus.COMPLETE,
    "done": DiamondsStatus.COMPLETE,
    "closed": DiamondsStatus.COMPLETE,
    "resolved": DiamondsStatus.COMPLETE,
    "cancelled": DiamondsStatus.CANCELLED,
    "canceled": DiamondsStatus.CANCELLED,
}


def _to_diamonds_status(value: str) -> DiamondsStatus:
    """Map a free-form status string to the Diamonds Status enum."""
    return _INTERNAL_TO_DIAMONDS_STATUS.get(value.lower(), DiamondsStatus.TODO)


def _from_diamonds_issue(issue: Any) -> _IssueRecord:
    """Convert a Diamonds Issue (ABC) into the internal issue record."""
    status = issue.status
    status_str = (
        _DIAMONDS_TO_INTERNAL_STATUS[status]
        if isinstance(status, DiamondsStatus)
        else str(status)
    )
    return _IssueRecord(
        ticket_id=str(issue.id),
        title=str(issue.title),
        status=status_str,
        description=str(issue.description),
    )


class _DiamondsClientAdapter:
    """Adapt Team Diamonds' IssueTrackerClient to our internal issue shape."""

    def __init__(self, client: IssueTrackerClient) -> None:
        self._client = client

    def get_issue(self, issue_id: str) -> _IssueRecord:
        return _from_diamonds_issue(self._client.get_issue(issue_id))

    def get_issues(self, *, status: str = "open") -> list[_IssueRecord]:
        diamonds_status = _to_diamonds_status(status)
        return [
            _from_diamonds_issue(issue)
            for issue in self._client.get_issues(status=diamonds_status)
        ]

    def create_issue(self, *, title: str, description: str) -> _IssueRecord:
        return _from_diamonds_issue(
            self._client.create_issue(title=title, description=description),
        )

    def update_issue(self, issue_id: str, new_status: str) -> None:
        diamonds_status = _to_diamonds_status(new_status)
        update = DiamondsIssueUpdate(status=diamonds_status)
        self._client.update_issue(issue_id, update)

    def delete_issue(self, issue_id: str) -> None:
        self._client.delete_issue(issue_id)


# ---------------------------------------------------------------------------
# Cross-vertical: Calendar (Team 12 — Outlook Calendar)
# ---------------------------------------------------------------------------


_calendar_client_factory: Callable[[], CalendarClient] | None = None


def register_calendar_client_factory(
    factory: Callable[[], CalendarClient] | None,
) -> None:
    """Register or clear the cross-vertical Calendar Client factory.

    Mirrors the HW1 ``register_client`` pattern so a concrete calendar
    implementation (Outlook, Google Calendar, etc.) can be injected without
    coupling the chat service to any provider SDK.
    """
    global _calendar_client_factory  # noqa: PLW0603
    _calendar_client_factory = factory


def get_calendar_client() -> CalendarClient | None:
    """Return the registered Calendar Client, or None if unset."""
    if _calendar_client_factory is None:
        return None
    return _calendar_client_factory()


@dataclass
class _EventRecord:
    """Internal normalised calendar event (provider-agnostic)."""

    event_id: str
    title: str
    starts_at: str
    ends_at: str
    location: str | None
    description: str | None


def _from_calendar_event(event: Any) -> _EventRecord:
    """Convert a Calendar ``Event`` ABC into the internal event record."""
    return _EventRecord(
        event_id=str(event.id),
        title=str(event.title),
        starts_at=event.starts_at.isoformat(),
        ends_at=event.ends_at.isoformat(),
        location=event.location,
        description=event.description,
    )


def _parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO 8601 timestamp; assume UTC if no tz is supplied."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


class _CalendarClientAdapter:
    """Adapt Team 12's ``calendar_client_api.Client`` to internal event shape."""

    def __init__(self, client: CalendarClient) -> None:
        self._client = client

    def list_events(self, *, days: int = 7) -> list[_EventRecord]:
        start = datetime.now(UTC)
        end = start + timedelta(days=days)
        return [
            _from_calendar_event(event)
            for event in self._client.list_events(start=start, end=end)
        ]

    def get_event(self, event_id: str) -> _EventRecord:
        return _from_calendar_event(self._client.get_event(event_id))

    def create_event(
        self,
        *,
        title: str,
        starts_at: str,
        ends_at: str,
        location: str | None = None,
        description: str | None = None,
    ) -> _EventRecord:
        event = self._client.create_event(
            title=title,
            starts_at=_parse_iso_datetime(starts_at),
            ends_at=_parse_iso_datetime(ends_at),
            location=location,
            description=description,
        )
        return _from_calendar_event(event)

    def update_event(  # noqa: PLR0913
        self,
        event_id: str,
        *,
        title: str | None = None,
        starts_at: str | None = None,
        ends_at: str | None = None,
        location: str | None = None,
        description: str | None = None,
    ) -> _EventRecord:
        patch = CalendarEventPatch(
            title=title,
            starts_at=_parse_iso_datetime(starts_at) if starts_at else None,
            ends_at=_parse_iso_datetime(ends_at) if ends_at else None,
            location=location,
            description=description,
        )
        return _from_calendar_event(self._client.update_event(event_id, patch))

    def cancel_event(self, event_id: str) -> None:
        self._client.delete_event(event_id)


def _build_calendar_client() -> _CalendarClientAdapter:
    """Resolve the registered Calendar client or fail with HTTP 503.

    Returns the adapter wrapping a concrete ``calendar_client_api.Client``;
    raises 503 if nothing is registered (cross-vertical dep not configured).
    """
    client = get_calendar_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No calendar client registered.",
        )
    return _CalendarClientAdapter(client)


def _cancel_event_tool(event_id: str) -> str:
    """AI tool wrapper: cancel an event and return a JSON ack."""
    _build_calendar_client().cancel_event(event_id)
    return json.dumps({"event_id": event_id, "status": "cancelled"})


class _TicketClientAdapter:
    """Normalize the legacy Trello-style client to the Jira issue contract."""

    def __init__(self, client: object) -> None:
        self._client = client

    def get_issue(self, issue_id: str) -> object:
        return self._client.get_ticket(issue_id)  # type: ignore[attr-defined]

    def get_issues(self, *, status: str = "open") -> list[object]:
        return list(self._client.get_tickets(status=status))  # type: ignore[attr-defined]

    def create_issue(self, *, title: str, description: str) -> object:
        return self._client.create_ticket(title, description)  # type: ignore[attr-defined]

    def update_issue(self, issue_id: str, new_status: str) -> None:
        self._client.update_ticket_status(issue_id, new_status)  # type: ignore[attr-defined]

    def delete_issue(self, issue_id: str) -> None:
        self._client.delete_ticket(issue_id)  # type: ignore[attr-defined]


class _JiraClientAdapter:
    """Normalize a Jira-style client to the methods used by this service."""

    def __init__(self, client: object) -> None:
        self._client = client

    def get_issue(self, issue_id: str) -> object:
        return self._client.get_issue(issue_id)  # type: ignore[attr-defined]

    def get_issues(self, *, status: str = "open") -> list[object]:
        return list(self._client.get_issues(status=_map_issue_status(status)))  # type: ignore[attr-defined]

    def create_issue(self, *, title: str, description: str) -> object:
        return self._client.create_issue(title=title, description=description)  # type: ignore[attr-defined]

    def update_issue(self, issue_id: str, new_status: str) -> object:
        if IssueUpdate is None or IssueStatus is None:
            raise RuntimeError("Jira issue update types are unavailable.")
        return self._client.update_issue(
            issue_id,
            IssueUpdate(status=_map_issue_status(new_status)),
        )

    def delete_issue(self, issue_id: str) -> None:
        self._client.delete_issue(issue_id)  # type: ignore[attr-defined]


@dataclass
class _IssueRecord:
    """Minimal normalized issue record for service responses."""

    ticket_id: str
    title: str
    status: str
    description: str


def _normalize_issue_payload(payload: dict[str, Any]) -> _IssueRecord:
    """Map Jira payload fields into the internal issue shape."""
    issue_id = str(payload.get("id", ""))
    title = str(payload.get("title", ""))
    status = str(payload.get("status", ""))
    description = str(payload.get("desc", payload.get("description", "")))
    return _IssueRecord(
        ticket_id=issue_id,
        title=title,
        status=status,
        description=description,
    )


def _map_to_jira_status(status_name: str) -> str:
    """Map generic statuses to Team Diamonds service status strings."""
    normalized = status_name.strip().lower()
    if normalized in {"todo", "to_do", "open", "backlog", "new"}:
        return "Status.TO_DO"
    if normalized in {"in_progress", "in progress", "working", "development"}:
        return "Status.IN_PROGRESS"
    if normalized in {"complete", "completed", "done", "closed", "resolved"}:
        return "Status.COMPLETED"
    return "Status.CANCELLED"

_HTTP_UNPROCESSABLE_ENTITY = 422
class _RemoteJiraHttpClient:
    """Direct HTTP adapter for Team Diamonds deployed Jira service."""

    def __init__(self, base_url: str, access_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {access_token}"}

    def get_issue(self, issue_id: str) -> _IssueRecord:
        try:
            response = httpx.get(
                f"{self._base_url}/issues/{issue_id}",
                headers=self._headers,
                timeout=20.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"Failed to fetch issue {issue_id}: {exc}"
            raise ValueError(msg) from exc

        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Invalid issue response payload")
        return _normalize_issue_payload(payload)

    def get_issues(self, *, status: str = "open") -> list[_IssueRecord]:
        params: dict[str, Any] = {}
        normalized = status.strip().lower()
        if status and normalized not in {"open", "todo", "to_do", "backlog", "new"}:
            params["status"] = _map_to_jira_status(status)

        try:
            response = httpx.get(
                f"{self._base_url}/issues",
                headers=self._headers,
                params=params,
                timeout=20.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if (
                exc.response is not None
                and exc.response.status_code == _HTTP_UNPROCESSABLE_ENTITY
                and params
            ):
                response = httpx.get(
                    f"{self._base_url}/issues",
                    headers=self._headers,
                    timeout=20.0,
                )
                response.raise_for_status()
            else:
                msg = f"Failed to fetch issues: {exc}"
                raise ValueError(msg) from exc
        except httpx.HTTPError as exc:
            msg = f"Failed to fetch issues: {exc}"
            raise ValueError(msg) from exc

        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Invalid issues response payload")

        issues = payload.get("issues", [])
        if not isinstance(issues, list):
            raise TypeError("Invalid issues list payload")
        return [
            _normalize_issue_payload(issue)
            for issue in issues
            if isinstance(issue, dict)
        ]

    def create_issue(self, *, title: str, description: str) -> _IssueRecord:
        body = {
            "title": title,
            "desc": description,
        }
        try:
            response = httpx.post(
                f"{self._base_url}/issues",
                headers=self._headers,
                json=body,
                timeout=20.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"Failed to create issue: {exc}"
            raise ValueError(msg) from exc

        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Invalid create issue response payload")
        return _normalize_issue_payload(payload)

    def update_issue(self, issue_id: str, new_status: str) -> _IssueRecord:
        body = {"status": _map_to_jira_status(new_status)}
        try:
            response = httpx.put(
                f"{self._base_url}/issues/{issue_id}",
                headers=self._headers,
                json=body,
                timeout=20.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"Failed to update issue {issue_id}: {exc}"
            raise ValueError(msg) from exc

        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Invalid update issue response payload")
        return _normalize_issue_payload(payload)

    def delete_issue(self, issue_id: str) -> None:
        try:
            response = httpx.delete(
                f"{self._base_url}/issues/{issue_id}",
                headers=self._headers,
                timeout=20.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"Failed to delete issue {issue_id}: {exc}"
            raise ValueError(msg) from exc


def _map_issue_status(status_name: str) -> object:
    normalized = status_name.strip().lower()
    if IssueStatus is None:
        return normalized
    if normalized in {"todo", "to_do", "open", "backlog", "new"}:
        return IssueStatus.TODO
    if normalized in {"in_progress", "in progress", "working", "development"}:
        return IssueStatus.IN_PROGRESS
    if normalized in {"complete", "completed", "done", "closed", "resolved"}:
        return IssueStatus.COMPLETE
    return IssueStatus.CANCELLED


def _sanitize_bearer_token(token: str) -> str:
    return "".join(token.split())


def _build_issue_client() -> (
    _DiamondsClientAdapter | _TicketClientAdapter | _RemoteJiraHttpClient
):
    """Build the cross-vertical issue tracker client.

    Resolution order:
    1. A registered Team Diamonds ``IssueTrackerClient`` factory (cross-vertical
       integration via ``register_diamonds_client_factory``).
    2. The Jira-shaped HTTP service if ``JIRA_SERVICE_BASE_URL`` and
       ``JIRA_SERVICE_ACCESS_TOKEN`` are set.
    3. The legacy Trello-style ``HttpTicketClient`` fallback.
    """
    diamonds_client = get_diamonds_client()
    if diamonds_client is not None:
        return _DiamondsClientAdapter(diamonds_client)

    jira_service_base_url = os.getenv("JIRA_SERVICE_BASE_URL")
    jira_service_access_token = os.getenv("JIRA_SERVICE_ACCESS_TOKEN")

    if jira_service_base_url and jira_service_access_token:
        cleaned_token = _sanitize_bearer_token(jira_service_access_token)
        if cleaned_token:
            return _RemoteJiraHttpClient(
                base_url=jira_service_base_url,
                access_token=cleaned_token,
            )

    from http_ticket_client_impl.client import HttpTicketClient

    ticket_base_url = os.getenv("TICKET_SERVICE_BASE_URL")
    if not ticket_base_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JIRA_SERVICE_BASE_URL or TICKET_SERVICE_BASE_URL is not configured",
        )

    board_id = os.getenv("TICKET_BOARD_ID", "")
    return _TicketClientAdapter(HttpTicketClient(ticket_base_url, board_id=board_id))


_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Chat Client Service — Telemetry Dashboard</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:system-ui,-apple-system,sans-serif;background:#0f172a;
       color:#e2e8f0;padding:2rem}
  h1{font-size:1.5rem;margin-bottom:1.5rem;color:#38bdf8}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
        gap:1rem;margin-bottom:2rem}
  .card{background:#1e293b;border-radius:12px;padding:1.25rem;
        border:1px solid #334155}
  .card .label{font-size:.75rem;text-transform:uppercase;letter-spacing:.05em;
               color:#94a3b8;margin-bottom:.25rem}
  .card .value{font-size:2rem;font-weight:700}
  .ok{color:#4ade80} .warn{color:#facc15} .err{color:#f87171}
  .bar-wrap{background:#334155;border-radius:6px;height:18px;overflow:hidden;
            margin-top:.5rem;display:flex}
  .bar-ok{background:#4ade80;height:100%}
  .bar-err{background:#f87171;height:100%}
  footer{margin-top:2rem;font-size:.75rem;color:#64748b;text-align:center}
  #updated{font-size:.75rem;color:#64748b;margin-bottom:1rem}
</style>
</head>
<body>
<h1>Telemetry Dashboard</h1>
<p id="updated">loading…</p>
<div class="grid">
  <div class="card">
    <div class="label">Total Requests</div>
    <div class="value" id="total">—</div>
  </div>
  <div class="card">
    <div class="label">Successful</div>
    <div class="value ok" id="success">—</div>
  </div>
  <div class="card">
    <div class="label">Failed</div>
    <div class="value err" id="failed">—</div>
  </div>
  <div class="card">
    <div class="label">Success Rate</div>
    <div class="value ok" id="srate">—</div>
    <div class="bar-wrap"><div class="bar-ok" id="sbar"></div>
    <div class="bar-err" id="fbar"></div></div>
  </div>
  <div class="card">
    <div class="label">Failure Rate</div>
    <div class="value err" id="frate">—</div>
  </div>
  <div class="card">
    <div class="label">Avg Latency</div>
    <div class="value warn" id="latency">—</div>
  </div>
</div>
<footer>OSPSD Team 9 — Chat Client Service &middot; auto-refreshes every 5 s</footer>
<script>
const $=id=>document.getElementById(id);
async function refresh(){
  try{
    const r=await fetch('/metrics');
    const d=await r.json();
    $('total').textContent=d.total_requests;
    $('success').textContent=d.successful_requests;
    $('failed').textContent=d.failed_requests;
    const sr=(d.success_rate*100).toFixed(1);
    const fr=(d.failure_rate*100).toFixed(1);
    $('srate').textContent=sr+'%';
    $('frate').textContent=fr+'%';
    const lat=d.average_latency_ms.toFixed(1);
    $('latency').textContent=lat+' ms';
    $('sbar').style.width=sr+'%';
    $('fbar').style.width=fr+'%';
    const t=new Date().toLocaleTimeString();
    $('updated').textContent='Updated: '+t;
  }catch(e){$('updated').textContent='Error';}
}
refresh();
setInterval(refresh,5000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Health & Metrics
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report service health."""
    return HealthResponse(status="ok")


@app.get("/metrics", response_model=MetricsSnapshot)
def metrics() -> MetricsSnapshot:
    """Return current telemetry snapshot."""
    return _build_metrics_snapshot()


def _escape_label(value: str) -> str:
    """Escape a Prometheus label value per text exposition rules."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


@app.get("/metrics/prometheus")
def metrics_prometheus() -> Response:
    """Expose telemetry in Prometheus text format for external scrapers."""
    snap = _build_metrics_snapshot()
    lines = [
        "# HELP chat_requests_total Total HTTP requests handled.",
        "# TYPE chat_requests_total counter",
        f"chat_requests_total {snap.total_requests}",
        "# HELP chat_requests_success_total Successful HTTP requests.",
        "# TYPE chat_requests_success_total counter",
        f"chat_requests_success_total {snap.successful_requests}",
        "# HELP chat_requests_failed_total Failed HTTP requests.",
        "# TYPE chat_requests_failed_total counter",
        f"chat_requests_failed_total {snap.failed_requests}",
        "# HELP chat_requests_domain_errors_total Requests that returned 4xx.",
        "# TYPE chat_requests_domain_errors_total counter",
        f"chat_requests_domain_errors_total {snap.domain_error_count}",
        "# HELP chat_requests_infra_errors_total Requests that returned 5xx.",
        "# TYPE chat_requests_infra_errors_total counter",
        f"chat_requests_infra_errors_total {snap.infra_error_count}",
        "# HELP chat_success_rate Ratio of successful to total requests.",
        "# TYPE chat_success_rate gauge",
        f"chat_success_rate {snap.success_rate}",
        "# HELP chat_failure_rate Ratio of failed to total requests.",
        "# TYPE chat_failure_rate gauge",
        f"chat_failure_rate {snap.failure_rate}",
        "# HELP chat_avg_latency_ms Average request latency in ms.",
        "# TYPE chat_avg_latency_ms gauge",
        f"chat_avg_latency_ms {snap.average_latency_ms}",
        "# HELP chat_requests_by_route_total Requests by route, method, status_class.",
        "# TYPE chat_requests_by_route_total counter",
    ]

    for entry in snap.by_route:
        route = _escape_label(entry.route)
        method = _escape_label(entry.method)
        for status_class, count in (
            ("ok", entry.ok_count),
            ("domain_error", entry.domain_error_count),
            ("infra_error", entry.infra_error_count),
        ):
            if count == 0:
                continue
            lines.append(
                'chat_requests_by_route_total'
                f'{{route="{route}",method="{method}",'
                f'status_class="{status_class}"}} {count}',
            )

    lines.extend([
        "# HELP chat_request_latency_ms_avg Avg request latency by route, method.",
        "# TYPE chat_request_latency_ms_avg gauge",
    ])
    for entry in snap.by_route:
        route = _escape_label(entry.route)
        method = _escape_label(entry.method)
        lines.append(
            'chat_request_latency_ms_avg'
            f'{{route="{route}",method="{method}"}} {entry.average_latency_ms}',
        )

    ai = snap.ai_usage
    lines.extend([
        "# HELP chat_ai_calls_total Total AI provider calls completed.",
        "# TYPE chat_ai_calls_total counter",
        f"chat_ai_calls_total {ai.calls_total}",
        "# HELP chat_ai_prompt_tokens_total Cumulative prompt tokens consumed.",
        "# TYPE chat_ai_prompt_tokens_total counter",
        f"chat_ai_prompt_tokens_total {ai.prompt_tokens_total}",
        "# HELP chat_ai_completion_tokens_total Cumulative completion tokens consumed.",
        "# TYPE chat_ai_completion_tokens_total counter",
        f"chat_ai_completion_tokens_total {ai.completion_tokens_total}",
        "# HELP chat_ai_total_tokens_total Cumulative total tokens consumed.",
        "# TYPE chat_ai_total_tokens_total counter",
        f"chat_ai_total_tokens_total {ai.total_tokens_total}",
        "# HELP chat_ai_estimated_cost_usd_total Approximate USD cost of AI calls.",
        "# TYPE chat_ai_estimated_cost_usd_total counter",
        f"chat_ai_estimated_cost_usd_total {ai.estimated_cost_usd_total}",
    ])

    lines.append("")
    return Response(
        content="\n".join(lines),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/dashboard")
def dashboard() -> Response:
    """Serve an HTML telemetry dashboard that auto-refreshes metrics."""
    html = _DASHBOARD_HTML
    return Response(content=html, media_type="text/html")


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


@app.post(
    "/auth/sessions",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_auth_session() -> AuthSessionResponse:
    """Create a new pending auth session."""
    settings = get_settings()
    session = _session_store.create_session()
    return AuthSessionResponse(
        session_id=session.session_id,
        authenticated=False,
        login_url=_build_login_url(settings, session.session_id),
        status_url=_build_status_url(settings, session.session_id),
    )


@app.get("/auth/login")
def auth_login(
    session_id: Annotated[str, Query(min_length=1)],
) -> RedirectResponse:
    """Redirect the browser to Slack's OAuth consent page."""
    settings = get_settings()
    _session_store.require_session(session_id)
    state = secrets.token_urlsafe(32)
    _session_store.bind_state(session_id, state)
    slack_authorization_url = _build_slack_authorization_url(settings, state)
    return RedirectResponse(
        url=slack_authorization_url,
        status_code=status.HTTP_302_FOUND,
    )


@app.get("/auth/callback", response_model=AuthCallbackResponse)
def auth_callback(
    code: str = "",
    state: str = "",
    error: str = "",
) -> AuthCallbackResponse:
    """Complete the Slack OAuth authorization-code flow."""
    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Slack OAuth error: {error}",
        )
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No code provided.",
        )
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No state provided.",
        )

    pending_session = _session_store.pop_session_for_state(state)
    if pending_session is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state.",
        )

    payload = _exchange_slack_code_for_token(code=code, settings=get_settings())
    if payload.get("ok") is not True:
        oauth_error = payload.get("error", "unknown_error")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Slack token exchange failed: {oauth_error}",
        )

    slack_bot_token = payload.get("access_token")
    if not isinstance(slack_bot_token, str) or not slack_bot_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Slack response missing access_token.",
        )

    _session_store.authenticate_session(
        session_id=pending_session.session_id,
        slack_bot_token=slack_bot_token,
        team_name=_extract_team_name(payload),
    )
    return AuthCallbackResponse(
        status="ok",
        message="Authentication successful. You can return to the client.",
    )


@app.get(
    "/auth/sessions/{session_id}",
    response_model=AuthSessionStatusResponse,
)
def get_auth_session(session_id: str) -> AuthSessionStatusResponse:
    """Return the current status of an auth session."""
    session = _session_store.require_session(session_id)
    return AuthSessionStatusResponse(
        session_id=session.session_id,
        authenticated=session.slack_bot_token is not None,
        team_name=session.team_name,
    )


@app.delete(
    "/auth/sessions/{session_id}",
    response_model=LogoutResponse,
)
def delete_auth_session(session_id: str) -> LogoutResponse:
    """Delete an auth session and any stored Slack credentials."""
    _session_store.delete_session(session_id)
    return LogoutResponse(status="ok")


# ---------------------------------------------------------------------------
# Channel endpoints
# ---------------------------------------------------------------------------


@app.get("/channels", response_model=ListChannelsResponse)
def list_channels(
    client: Annotated[ChatClient, Depends(_get_authenticated_client)],
) -> ListChannelsResponse:
    """List Slack channels for the authenticated session."""
    channels = [
        ChannelModel.from_dto(channel)
        for channel in client.get_channels()
    ]
    return ListChannelsResponse(channels=channels)


@app.get("/channels/{channel_id}", response_model=GetChannelResponse)
def get_channel(
    channel_id: str,
    client: Annotated[ChatClient, Depends(_get_authenticated_client)],
) -> GetChannelResponse:
    """Get a single Slack channel by ID."""
    try:
        channel = client.get_channel(channel_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return GetChannelResponse.from_dto(channel)


# ---------------------------------------------------------------------------
# Message endpoints
# ---------------------------------------------------------------------------


@app.post("/messages", response_model=MessageModel)
def send_message(
    payload: SendMessageRequest,
    client: Annotated[ChatClient, Depends(_get_authenticated_client)],
) -> MessageModel:
    """Send a message to a Slack channel."""
    try:
        message = client.send_message(channel_id=payload.channel, text=payload.text)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return MessageModel.from_dto(message)


@app.get("/messages", response_model=GetMessagesResponse)
def get_messages(
    client: Annotated[ChatClient, Depends(_get_authenticated_client)],
    channel: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=200)] = 10,
    cursor: Annotated[str | None, Query()] = None,
) -> GetMessagesResponse:
    """Get recent messages from a Slack channel."""
    messages = client.get_messages(channel_id=channel, limit=limit, cursor=cursor)
    return GetMessagesResponse(
        messages=[MessageModel.from_dto(message) for message in messages],
    )


@app.get("/messages/{message_id:path}", response_model=MessageModel)
def get_message(
    message_id: str,
    client: Annotated[ChatClient, Depends(_get_authenticated_client)],
) -> MessageModel:
    """Get a single message by ID."""
    try:
        message = client.get_message(message_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return MessageModel.from_dto(message)


@app.delete("/messages/{message_id:path}", response_model=DeleteMessageResponse)
def delete_message(
    message_id: str,
    client: Annotated[ChatClient, Depends(_get_authenticated_client)],
) -> DeleteMessageResponse:
    """Delete a message by ID."""
    try:
        client.delete_message(message_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return DeleteMessageResponse(status="ok")


@app.post("/ai/chat", response_model=AiChatResponse)
def ai_chat(
    payload: AiChatRequest,
    client: Annotated[ChatClient, Depends(_get_authenticated_client)],
) -> AiChatResponse:
    """Send a natural-language prompt to the AI assistant.

    The assistant has access to chat domain tools (list channels, send
    messages, fetch history) so it can take real actions on your behalf.
    """
    tools = [
        AiTool(
            name="get_channels",
            description="List all available Slack channels",
            parameters={},
            handler=lambda: json.dumps([
                {"channel_id": c.channel_id, "name": c.name}
                for c in client.get_channels()
            ]),
        ),
        AiTool(
            name="send_message",
            description="Send a text message to a Slack channel",
            parameters={
                "channel_id": {"type": "string", "description": "Channel ID"},
                "text": {"type": "string", "description": "Message text"},
            },
            handler=lambda channel_id, text: json.dumps({
                "message_id": client.send_message(
                    channel_id=channel_id, text=text,
                ).message_id,
            }),
        ),
        AiTool(
            name="get_messages",
            description="Fetch recent messages from a Slack channel",
            parameters={
                "channel_id": {"type": "string", "description": "Channel ID"},
                "limit": {
                    "type": "integer",
                    "description": "Max messages to fetch (default 10)",
                },
            },
            handler=lambda channel_id, limit=10: json.dumps([
                {"text": m.text, "sender": m.sender, "timestamp": m.timestamp}
                for m in client.get_messages(channel_id=channel_id, limit=limit)
            ]),
        ),
        AiTool(
            name="get_issues",
            description="List Jira issues filtered by status",
            parameters={
                "status": {
                    "type": "string",
                    "description": (
                        "Issue status (open, in_progress, complete, cancelled, etc.)"
                    ),
                },
            },
            handler=lambda status="open": json.dumps([
                {
                    "issue_id": ticket.ticket_id,  # type: ignore[attr-defined]
                    "title": ticket.title,  # type: ignore[attr-defined]
                    "status": ticket.status,  # type: ignore[attr-defined]
                    "description": ticket.description,  # type: ignore[attr-defined]
                }
                for ticket in _build_issue_client().get_issues(status=status)
            ]),
        ),
        AiTool(
            name="create_issue",
            description="Create a Jira issue in the external issue tracker",
            parameters={
                "title": {"type": "string", "description": "Issue title"},
                "description": {
                    "type": "string",
                    "description": "Issue description",
                },
            },
            handler=lambda title, description: json.dumps({
                "issue_id": _build_issue_client().create_issue(  # type: ignore[attr-defined]
                    title=title,
                    description=description,
                ).ticket_id,
                "status": "created",
            }),
        ),
        AiTool(
            name="update_issue_status",
            description="Update Jira issue status in the external issue tracker",
            parameters={
                "issue_id": {
                    "type": "string",
                    "description": "Issue identifier",
                },
                "new_status": {
                    "type": "string",
                    "description": "New status value",
                },
            },
            handler=lambda issue_id, new_status: json.dumps({
                "issue_id": issue_id,
                "new_status": new_status,
                "result": _build_issue_client().update_issue(
                    issue_id=issue_id,
                    new_status=new_status,
                )
                or "ok",
            }),
        ),
        AiTool(
            name="list_events",
            description=(
                "List upcoming calendar events from the registered "
                "calendar provider (Outlook / Google)."
            ),
            parameters={
                "days": {
                    "type": "integer",
                    "description": (
                        "Window size in days, starting from now (default 7)."
                    ),
                },
            },
            handler=lambda days=7: json.dumps([
                {
                    "event_id": e.event_id,
                    "title": e.title,
                    "starts_at": e.starts_at,
                    "ends_at": e.ends_at,
                    "location": e.location,
                }
                for e in _build_calendar_client().list_events(days=int(days))
            ]),
        ),
        AiTool(
            name="schedule_event",
            description=(
                "Schedule a new calendar event in the registered "
                "calendar provider."
            ),
            parameters={
                "title": {"type": "string", "description": "Event title."},
                "starts_at": {
                    "type": "string",
                    "description": "ISO 8601 start datetime.",
                },
                "ends_at": {
                    "type": "string",
                    "description": "ISO 8601 end datetime.",
                },
                "location": {
                    "type": "string",
                    "description": "Optional location.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional event description / agenda.",
                },
            },
            handler=lambda title, starts_at, ends_at,
            location=None,
            description=None: json.dumps({
                "event_id": _build_calendar_client().create_event(
                    title=title,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    location=location,
                    description=description,
                ).event_id,
                "status": "scheduled",
            }),
        ),
        AiTool(
            name="cancel_event",
            description="Cancel a calendar event by ID.",
            parameters={
                "event_id": {
                    "type": "string",
                    "description": "Event identifier returned by list_events.",
                },
            },
            handler=_cancel_event_tool,
        ),
    ]

    try:
        ai = get_ai_client()
        context: dict[str, Any] = {"session_active": True}
        if payload.channel:
            context["channel"] = payload.channel
        reply = ai.send_message_with_tools(
            prompt=payload.prompt,
            tools=tools,
            context=context,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    _record_ai_usage(ai.get_last_usage())
    return AiChatResponse(reply=reply)


@app.get("/issues", response_model=ListIssuesResponse)
def list_issues(
    issue_status: Annotated[str, Query(alias="ticket_status")] = "open",
) -> ListIssuesResponse:
    """Fetch issues from the selected Jira integration path.

    Reads JIRA_SERVICE_BASE_URL / JIRA_SERVICE_ACCESS_TOKEN or the legacy
    TICKET_SERVICE_BASE_URL / TICKET_BOARD_ID fallback from the
    environment to locate the external ticket service.
    """
    issue_client = _build_issue_client()
    try:
        issues = issue_client.get_issues(status=issue_status)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return ListIssuesResponse(
        issues=[IssueModel.from_dto(t) for t in issues],  # type: ignore[arg-type]
    )


@app.get("/tickets", response_model=ListIssuesResponse)
def list_tickets(
    ticket_status: Annotated[str, Query()] = "open",
) -> ListIssuesResponse:
    """Backward-compatible alias for /issues."""
    return list_issues(issue_status=ticket_status)


@app.get("/issues/{issue_id}", response_model=GetIssueResponse)
def get_issue(issue_id: str) -> GetIssueResponse:
    """Fetch one issue by ID from the selected Jira provider."""
    issue_client = _build_issue_client()
    try:
        issue = issue_client.get_issue(issue_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return GetIssueResponse(issue=IssueModel.from_dto(issue))  # type: ignore[arg-type]


@app.get("/tickets/{ticket_id}", response_model=GetIssueResponse)
def get_ticket(ticket_id: str) -> GetIssueResponse:
    """Backward-compatible alias for /issues/{issue_id}."""
    return get_issue(issue_id=ticket_id)


@app.post(
    "/issues",
    response_model=CreateIssueResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_issue(payload: CreateIssueRequest) -> CreateIssueResponse:
    """Create an issue in the selected Jira provider."""
    issue_client = _build_issue_client()
    try:
        issue = issue_client.create_issue(
            title=payload.title,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return CreateIssueResponse(issue=IssueModel.from_dto(issue))  # type: ignore[arg-type]


@app.post(
    "/tickets",
    response_model=CreateIssueResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_ticket(payload: CreateIssueRequest) -> CreateIssueResponse:
    """Backward-compatible alias for /issues."""
    return create_issue(payload)


@app.patch(
    "/issues/{issue_id}/status",
    response_model=UpdateIssueStatusResponse,
)
def update_issue_status(
    issue_id: str,
    payload: UpdateIssueStatusRequest,
) -> UpdateIssueStatusResponse:
    """Update an issue's status in the selected Jira provider."""
    issue_client = _build_issue_client()
    try:
        issue_client.update_issue(
            issue_id=issue_id,
            new_status=payload.new_status,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return UpdateIssueStatusResponse(status="ok", issue_id=issue_id)


@app.patch(
    "/tickets/{ticket_id}/status",
    response_model=UpdateIssueStatusResponse,
)
def update_ticket_status(
    ticket_id: str,
    payload: UpdateIssueStatusRequest,
) -> UpdateIssueStatusResponse:
    """Backward-compatible alias for /issues/{issue_id}/status."""
    return update_issue_status(issue_id=ticket_id, payload=payload)


def create_app() -> FastAPI:
    """Return the configured FastAPI application."""
    return app


# ---------------------------------------------------------------------------
# Demo registration: in-memory calendar
# ---------------------------------------------------------------------------


def _maybe_register_demo_calendar() -> None:
    """Auto-register an in-memory calendar when CALENDAR_DEMO_MODE is true.

    Lets the deployed service exercise the cross-vertical schedule_event /
    list_events / cancel_event AI tools for the demo video without
    requiring real Outlook OAuth credentials. The flag is opt-in so
    production deployments are not silently swapped onto a stub backend.

    Uses a process-wide singleton so events scheduled by one /ai/chat call
    are visible to subsequent list_events / cancel_event calls.
    """
    flag = os.getenv("CALENDAR_DEMO_MODE", "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return
    if get_calendar_client() is not None:
        return
    from ._demo_calendar import InMemoryCalendarClient

    singleton = InMemoryCalendarClient()
    register_calendar_client_factory(lambda: singleton)


_maybe_register_demo_calendar()
