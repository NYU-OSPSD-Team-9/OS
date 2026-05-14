"""In-memory calendar implementation used for the demo video.

This is **not** a production calendar — it lives entirely in process memory
and is reset on every redeploy. It exists so the cross-vertical
``schedule_event`` / ``list_events`` / ``cancel_event`` AI tools can be
demonstrated end-to-end without OAuth credentials for a real provider.

Activation is opt-in: set ``CALENDAR_DEMO_MODE=true`` in the deployment
environment. When the env var is unset, the chat service returns HTTP 503
from the calendar tools, so production cannot accidentally fall back to
this stub.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from calendar_client_api import (
    Client as CalendarClient,
)
from calendar_client_api import (
    Event as CalendarEvent,
)
from calendar_client_api.exceptions import CalendarNotFoundError

if TYPE_CHECKING:
    from datetime import datetime

    from calendar_client_api import EventPatch as CalendarEventPatch


class _InMemoryEvent(CalendarEvent):
    """Concrete Event backed by simple instance attributes."""

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


class InMemoryCalendarClient(CalendarClient):
    """Thread-safe in-memory implementation of ``calendar_client_api.Client``.

    Suitable for demos and integration tests. Not durable — events are lost
    on process restart.
    """

    def __init__(self) -> None:
        self._events: dict[str, _InMemoryEvent] = {}
        self._lock = threading.Lock()
        self._next_id = 1

    def _allocate_id(self) -> str:
        nid = self._next_id
        self._next_id += 1
        return f"DEMO-{nid}"

    def get_event(self, event_id: str) -> CalendarEvent:
        with self._lock:
            event = self._events.get(event_id)
            if event is None:
                msg = f"Event not found: {event_id}"
                raise CalendarNotFoundError(msg)
            return event

    def list_events(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        types: list[str] | None = None,
    ) -> list[CalendarEvent]:
        del types
        with self._lock:
            events: list[CalendarEvent] = []
            for event in self._events.values():
                if start is not None and event.ends_at < start:
                    continue
                if end is not None and event.starts_at > end:
                    continue
                events.append(event)
            events.sort(key=lambda ev: ev.starts_at)
            return events

    def create_event(
        self,
        title: str,
        starts_at: datetime,
        ends_at: datetime,
        location: str | None = None,
        description: str | None = None,
    ) -> CalendarEvent:
        with self._lock:
            event_id = self._allocate_id()
            event = _InMemoryEvent(
                event_id, title, starts_at, ends_at, location, description,
            )
            self._events[event_id] = event
            return event

    def delete_event(self, event_id: str) -> None:
        with self._lock:
            if event_id not in self._events:
                msg = f"Event not found: {event_id}"
                raise CalendarNotFoundError(msg)
            del self._events[event_id]

    def update_event(
        self, event_id: str, payload: CalendarEventPatch,
    ) -> CalendarEvent:
        with self._lock:
            existing = self._events.get(event_id)
            if existing is None:
                msg = f"Event not found: {event_id}"
                raise CalendarNotFoundError(msg)
            updated = _InMemoryEvent(
                event_id,
                payload.title if payload.title is not None else existing.title,
                payload.starts_at
                if payload.starts_at is not None
                else existing.starts_at,
                payload.ends_at
                if payload.ends_at is not None
                else existing.ends_at,
                payload.location
                if payload.location is not None
                else existing.location,
                payload.description
                if payload.description is not None
                else existing.description,
            )
            self._events[event_id] = updated
            return updated
