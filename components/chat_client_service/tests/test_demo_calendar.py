"""Tests for the in-memory demo calendar and CALENDAR_DEMO_MODE auto-register."""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest import mock

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
from calendar_client_api import EventPatch
from calendar_client_api.exceptions import CalendarNotFoundError
from chat_client_service import main as service_main
from chat_client_service._demo_calendar import InMemoryCalendarClient


def _t(offset_minutes: int) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=offset_minutes)


def test_create_and_get_event_roundtrip() -> None:
    """A created event must be retrievable by the returned id."""
    calendar = InMemoryCalendarClient()
    created = calendar.create_event(
        title="Standup",
        starts_at=_t(60),
        ends_at=_t(90),
        location="Zoom",
        description="daily",
    )
    assert created.id.startswith("DEMO-")
    fetched = calendar.get_event(created.id)
    assert fetched.title == "Standup"
    assert fetched.location == "Zoom"


def test_get_event_missing_raises_not_found() -> None:
    """Looking up an unknown event raises CalendarNotFoundError."""
    calendar = InMemoryCalendarClient()
    with pytest.raises(CalendarNotFoundError):
        calendar.get_event("does-not-exist")


def test_list_events_filters_by_window() -> None:
    """Events outside the [start, end] window are excluded."""
    calendar = InMemoryCalendarClient()
    near = calendar.create_event(
        title="Today", starts_at=_t(10), ends_at=_t(40),
    )
    far = calendar.create_event(
        title="Next week",
        starts_at=_t(60 * 24 * 8),
        ends_at=_t(60 * 24 * 8 + 30),
    )
    visible = calendar.list_events(start=_t(0), end=_t(60 * 24))
    ids = {ev.id for ev in visible}
    assert near.id in ids
    assert far.id not in ids


def test_list_events_returned_in_chronological_order() -> None:
    """list_events should return events sorted by starts_at."""
    calendar = InMemoryCalendarClient()
    later = calendar.create_event(
        title="2pm", starts_at=_t(120), ends_at=_t(150),
    )
    earlier = calendar.create_event(
        title="1pm", starts_at=_t(60), ends_at=_t(90),
    )
    out = calendar.list_events()
    assert [ev.id for ev in out] == [earlier.id, later.id]


def test_update_event_applies_partial_patch() -> None:
    """Only the fields explicitly set on the patch are changed."""
    calendar = InMemoryCalendarClient()
    created = calendar.create_event(
        title="Old", starts_at=_t(60), ends_at=_t(90), location="A",
    )
    updated = calendar.update_event(created.id, EventPatch(title="New"))
    assert updated.title == "New"
    assert updated.location == "A"  # untouched


def test_update_missing_event_raises() -> None:
    """Updating a non-existent event raises CalendarNotFoundError."""
    calendar = InMemoryCalendarClient()
    with pytest.raises(CalendarNotFoundError):
        calendar.update_event("nope", EventPatch(title="x"))


def test_delete_event_removes_it() -> None:
    """A deleted event is no longer returned by list_events."""
    calendar = InMemoryCalendarClient()
    created = calendar.create_event(
        title="ephemeral", starts_at=_t(60), ends_at=_t(90),
    )
    calendar.delete_event(created.id)
    assert not calendar.list_events()
    with pytest.raises(CalendarNotFoundError):
        calendar.get_event(created.id)


def test_delete_missing_event_raises() -> None:
    """Deleting a non-existent event raises CalendarNotFoundError."""
    calendar = InMemoryCalendarClient()
    with pytest.raises(CalendarNotFoundError):
        calendar.delete_event("nope")


# ---------------------------------------------------------------------------
# CALENDAR_DEMO_MODE auto-registration (call _maybe_register_demo_calendar
# directly rather than reloading the module — reload corrupts the global
# FastAPI app instance other tests share).
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_calendar_factory() -> Iterator[None]:
    """Save and restore the registered calendar factory around each test."""
    saved = service_main._calendar_client_factory
    service_main.register_calendar_client_factory(None)
    yield
    service_main._calendar_client_factory = saved


def test_demo_calendar_registered_when_env_flag_set() -> None:
    """CALENDAR_DEMO_MODE=true should register the in-memory client."""
    with mock.patch.dict(os.environ, {"CALENDAR_DEMO_MODE": "true"}, clear=False):
        service_main._maybe_register_demo_calendar()
        client = service_main.get_calendar_client()
    assert isinstance(client, InMemoryCalendarClient)


def test_demo_calendar_not_registered_when_env_flag_absent() -> None:
    """Without the env flag no calendar factory is auto-registered."""
    env = {k: v for k, v in os.environ.items() if k != "CALENDAR_DEMO_MODE"}
    with mock.patch.dict(os.environ, env, clear=True):
        service_main._maybe_register_demo_calendar()
        assert service_main.get_calendar_client() is None


def test_demo_calendar_does_not_clobber_existing_factory() -> None:
    """A pre-registered factory must not be replaced by the demo helper."""
    sentinel = InMemoryCalendarClient()
    service_main.register_calendar_client_factory(lambda: sentinel)
    with mock.patch.dict(os.environ, {"CALENDAR_DEMO_MODE": "true"}, clear=False):
        service_main._maybe_register_demo_calendar()
    assert service_main.get_calendar_client() is sentinel
