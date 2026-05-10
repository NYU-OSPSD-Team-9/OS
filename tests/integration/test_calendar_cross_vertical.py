"""Integration test: AI tool-call → Team 12 Calendar Client.

This is the second cross-vertical integration alongside the Diamonds
issue tracker. It exercises the full pathway:

- The Team 12 calendar interface (``calendar_client_api``) is pulled in
  from their HW-3 branch via ``pyproject.toml`` (``tool.uv.sources``).
- A concrete ``Client`` implementation is injected via the
  ``register_calendar_client_factory()`` DI hook.
- A fake ``AiClient`` triggers ``list_events``, ``schedule_event``, and
  ``cancel_event`` tools exposed by ``/ai/chat``.
- The tool handlers reach ``_CalendarClientAdapter``, which calls the
  injected calendar client.
- Only the calendar implementation is fake; the FastAPI service, the
  telemetry middleware, the AI tool dispatch loop, and the calendar
  resolution chain run for real.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Any

import pytest
from ai_client_api.client import AiClient, AiTool, register_ai_client
from calendar_client_api import (
    Client as CalendarClient,
)
from calendar_client_api import (
    Event as CalendarEvent,
)
from calendar_client_api import (
    EventPatch as CalendarEventPatch,
)
from chat_client_api.client import Channel, ChatClient, Message
from chat_client_service.main import (
    _get_authenticated_client,
    app,
    register_calendar_client_factory,
    reset_service_state,
)
from fastapi.testclient import TestClient


class _FakeEvent(CalendarEvent):
    """Minimal concrete Event for tests."""

    def __init__(  # noqa: PLR0913
        self,
        event_id: str,
        title: str,
        starts_at: datetime,
        ends_at: datetime,
        location: str | None = None,
        description: str | None = None,
    ) -> None:
        self._id = event_id
        self._title = title
        self._starts_at = starts_at
        self._ends_at = ends_at
        self._location = location
        self._description = description

    @property
    def id(self) -> str:
        return self._id

    @property
    def title(self) -> str:
        return self._title

    @property
    def starts_at(self) -> datetime:
        return self._starts_at

    @property
    def ends_at(self) -> datetime:
        return self._ends_at

    @property
    def location(self) -> str | None:
        return self._location

    @property
    def description(self) -> str | None:
        return self._description


class _FakeCalendarClient(CalendarClient):
    """Concrete CalendarClient capturing what the AI tool dispatches."""

    def __init__(self) -> None:
        seed_start = datetime.now(UTC) + timedelta(hours=2)
        self._events: dict[str, _FakeEvent] = {
            "EV-1": _FakeEvent(
                "EV-1",
                "Existing standup",
                seed_start,
                seed_start + timedelta(minutes=30),
                location="Zoom",
            ),
        }
        self.created: list[_FakeEvent] = []
        self.updated: list[tuple[str, CalendarEventPatch]] = []
        self.deleted: list[str] = []

    def get_event(self, event_id: str) -> CalendarEvent:
        return self._events[event_id]

    def list_events(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        types: list[str] | None = None,
    ) -> list[CalendarEvent]:
        out: list[CalendarEvent] = []
        for event in self._events.values():
            if start is not None and event.ends_at < start:
                continue
            if end is not None and event.starts_at > end:
                continue
            out.append(event)
        return out

    def create_event(
        self,
        title: str,
        starts_at: datetime,
        ends_at: datetime,
        location: str | None = None,
        description: str | None = None,
    ) -> CalendarEvent:
        event_id = f"EV-{len(self._events) + 1}"
        event = _FakeEvent(
            event_id, title, starts_at, ends_at, location, description,
        )
        self._events[event_id] = event
        self.created.append(event)
        return event

    def delete_event(self, event_id: str) -> None:
        self.deleted.append(event_id)
        self._events.pop(event_id, None)

    def update_event(
        self, event_id: str, payload: CalendarEventPatch,
    ) -> CalendarEvent:
        self.updated.append((event_id, payload))
        return self._events[event_id]


class _ToolCallingFakeAi(AiClient):
    """Fake AiClient that always invokes one configured tool."""

    def __init__(self, tool_name: str, tool_args: dict[str, Any]) -> None:
        self._tool_name = tool_name
        self._tool_args = tool_args
        self.last_handler_result: str | None = None

    def send_message(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        return f"fake reply: {prompt}"

    def send_message_with_tools(
        self,
        prompt: str,
        tools: list[AiTool],
        context: dict[str, Any] | None = None,
    ) -> str:
        tool_map = {t.name: t for t in tools}
        tool = tool_map[self._tool_name]
        if tool.handler is None:
            msg = f"tool {self._tool_name!r} has no handler"
            raise AssertionError(msg)
        result = tool.handler(**self._tool_args)
        self.last_handler_result = result
        return f"executed {self._tool_name}: {result}"


class _StubChat(ChatClient):
    def send_message(self, channel_id: str, text: str) -> Message:
        return Message(
            message_id=f"{channel_id}:0",
            channel=channel_id,
            text=text,
            sender="stub",
            timestamp="0",
        )

    def get_channels(self) -> list[Channel]:
        return []

    def get_channel(self, channel_id: str) -> Channel:
        return Channel(channel_id=channel_id, name="stub", is_private=False)

    def get_messages(
        self,
        channel_id: str,
        limit: int = 10,
        cursor: str | None = None,
    ) -> list[Message]:
        return []

    def get_message(self, message_id: str) -> Message:
        return Message(
            message_id=message_id,
            channel="",
            text="",
            sender="",
            timestamp="",
        )

    def delete_message(self, message_id: str) -> None:
        pass


def _stub_chat() -> _StubChat:
    return _StubChat()


@pytest.fixture
def calendar_client() -> Any:
    """Inject a fake CalendarClient and stub chat dependency."""
    reset_service_state()
    fake = _FakeCalendarClient()
    register_calendar_client_factory(lambda: fake)
    app.dependency_overrides[_get_authenticated_client] = _stub_chat
    yield fake
    register_calendar_client_factory(None)
    app.dependency_overrides.clear()


def test_ai_tool_call_lists_calendar_events(
    calendar_client: _FakeCalendarClient,
) -> None:
    """list_events tool reaches the injected calendar client."""
    fake_ai = _ToolCallingFakeAi(
        tool_name="list_events",
        tool_args={"days": 7},
    )
    register_ai_client(lambda: fake_ai)

    response = TestClient(app).post(
        "/ai/chat",
        json={"prompt": "what's on my calendar this week"},
    )

    assert response.status_code == HTTPStatus.OK
    events = json.loads(fake_ai.last_handler_result or "[]")
    assert {ev["event_id"] for ev in events} == {"EV-1"}
    assert calendar_client is not None  # fixture was used


def test_ai_tool_call_schedules_calendar_event(
    calendar_client: _FakeCalendarClient,
) -> None:
    """schedule_event tool calls Team 12's create_event."""
    starts = (datetime.now(UTC) + timedelta(hours=24)).replace(microsecond=0)
    ends = starts + timedelta(minutes=30)
    fake_ai = _ToolCallingFakeAi(
        tool_name="schedule_event",
        tool_args={
            "title": "AI-scheduled sync",
            "starts_at": starts.isoformat(),
            "ends_at": ends.isoformat(),
            "location": "Zoom",
            "description": "Triggered by the AI assistant",
        },
    )
    register_ai_client(lambda: fake_ai)

    response = TestClient(app).post(
        "/ai/chat",
        json={"prompt": "schedule a 30 min sync tomorrow"},
    )

    assert response.status_code == HTTPStatus.OK
    assert len(calendar_client.created) == 1
    created = calendar_client.created[0]
    assert created.title == "AI-scheduled sync"
    assert created.location == "Zoom"

    body = json.loads(fake_ai.last_handler_result or "{}")
    assert body["status"] == "scheduled"
    assert body["event_id"].startswith("EV-")


def test_ai_tool_call_cancels_calendar_event(
    calendar_client: _FakeCalendarClient,
) -> None:
    """cancel_event tool deletes through the injected calendar client."""
    fake_ai = _ToolCallingFakeAi(
        tool_name="cancel_event",
        tool_args={"event_id": "EV-1"},
    )
    register_ai_client(lambda: fake_ai)

    response = TestClient(app).post(
        "/ai/chat",
        json={"prompt": "cancel my standup"},
    )

    assert response.status_code == HTTPStatus.OK
    assert calendar_client.deleted == ["EV-1"]


def test_ai_tool_call_without_calendar_factory_returns_503(
    calendar_client: _FakeCalendarClient,
) -> None:
    """When the Calendar factory is unregistered, /ai/chat returns 503."""
    register_calendar_client_factory(None)
    fake_ai = _ToolCallingFakeAi(
        tool_name="list_events",
        tool_args={"days": 7},
    )
    register_ai_client(lambda: fake_ai)

    response = TestClient(
        app, raise_server_exceptions=False,
    ).post(
        "/ai/chat",
        json={"prompt": "list my events"},
    )
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
