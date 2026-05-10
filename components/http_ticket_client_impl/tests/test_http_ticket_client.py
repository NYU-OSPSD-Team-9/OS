"""Unit tests for the HTTP ticket client (Team 3 Trello adapter)."""

from __future__ import annotations

from typing import Any
from unittest import mock

import httpx
import pytest
from http_ticket_client_impl.client import HttpTicketClient
from ticket_client_api.client import Ticket

BOARD = "abc123"


def _make_response(
    *,
    status_code: int = 200,
    json_data: Any = None,
    raise_error: bool = False,
) -> mock.MagicMock:
    resp = mock.MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    if raise_error:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=mock.MagicMock(), response=resp,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def test_get_tickets_success() -> None:
    """get_tickets should map Team 3's IssueOut to Ticket objects."""
    client = HttpTicketClient("http://tickets.local", board_id=BOARD)
    fake_resp = _make_response(
        json_data=[
            {"id": 1, "title": "Bug", "state": "open", "body": "desc"},
            {"id": 2, "title": "Feat", "state": "closed", "body": "x"},
        ],
    )
    with mock.patch("httpx.get", return_value=fake_resp) as mock_get:
        tickets = client.get_tickets()

    mock_get.assert_called_once_with(
        f"http://tickets.local/boards/{BOARD}/issues",
        timeout=15.0,
    )
    assert len(tickets) == 1
    assert isinstance(tickets[0], Ticket)
    assert tickets[0].ticket_id == "1"
    assert tickets[0].status == "open"
    assert tickets[0].description == "desc"


def test_get_tickets_no_filter() -> None:
    """get_tickets with empty status should return all issues."""
    client = HttpTicketClient("http://tickets.local", board_id=BOARD)
    issue_list = [
        {"id": 1, "title": "A", "state": "open", "body": ""},
        {"id": 2, "title": "B", "state": "closed", "body": ""},
    ]
    fake_resp = _make_response(json_data=issue_list)
    with mock.patch("httpx.get", return_value=fake_resp):
        tickets = client.get_tickets(status="")
    assert len(tickets) == len(issue_list)


def test_get_tickets_failure_raises() -> None:
    """get_tickets should raise ValueError on HTTP error."""
    client = HttpTicketClient("http://tickets.local", board_id=BOARD)
    fake_resp = _make_response(raise_error=True)
    with mock.patch("httpx.get", return_value=fake_resp):
        with pytest.raises(ValueError, match="Failed to fetch tickets"):
            client.get_tickets()


def test_get_ticket_success() -> None:
    """get_ticket should map a single IssueOut to a Ticket."""
    client = HttpTicketClient("http://tickets.local", board_id=BOARD)
    fake_resp = _make_response(
        json_data={"id": 1, "title": "Bug", "state": "open", "body": "d"},
    )
    with mock.patch("httpx.get", return_value=fake_resp) as mock_get:
        ticket = client.get_ticket("1")

    mock_get.assert_called_once_with(
        f"http://tickets.local/boards/{BOARD}/issues/1",
        timeout=15.0,
    )
    assert ticket.ticket_id == "1"
    assert ticket.description == "d"


def test_get_ticket_not_found_raises() -> None:
    """get_ticket should raise ValueError on HTTP error."""
    client = HttpTicketClient("http://tickets.local", board_id=BOARD)
    fake_resp = _make_response(raise_error=True)
    with mock.patch("httpx.get", return_value=fake_resp):
        with pytest.raises(ValueError, match="Ticket not found"):
            client.get_ticket("999")


def test_create_ticket_success() -> None:
    """create_ticket should POST with title and body, return Ticket."""
    client = HttpTicketClient("http://tickets.local", board_id=BOARD)
    fake_resp = _make_response(
        json_data={"id": 5, "title": "New", "state": "open", "body": "d"},
    )
    with mock.patch("httpx.post", return_value=fake_resp) as mock_post:
        ticket = client.create_ticket("New", "d")

    mock_post.assert_called_once_with(
        f"http://tickets.local/boards/{BOARD}/issues",
        json={"title": "New", "body": "d"},
        timeout=15.0,
    )
    assert ticket.ticket_id == "5"


def test_create_ticket_failure_raises() -> None:
    """create_ticket should raise ValueError on HTTP error."""
    client = HttpTicketClient("http://tickets.local", board_id=BOARD)
    fake_resp = _make_response(raise_error=True)
    with mock.patch("httpx.post", return_value=fake_resp):
        with pytest.raises(ValueError, match="Failed to create ticket"):
            client.create_ticket("X", "Y")


def test_update_ticket_status_success() -> None:
    """update_ticket_status should POST to the close endpoint."""
    client = HttpTicketClient("http://tickets.local", board_id=BOARD)
    fake_resp = _make_response(json_data={"success": True})
    with mock.patch("httpx.post", return_value=fake_resp) as mock_post:
        client.update_ticket_status("1", "closed")

    mock_post.assert_called_once_with(
        f"http://tickets.local/boards/{BOARD}/issues/1/close",
        json=None,
        timeout=15.0,
    )


def test_update_ticket_status_failure_raises() -> None:
    """update_ticket_status should raise ValueError on HTTP error."""
    client = HttpTicketClient("http://tickets.local", board_id=BOARD)
    fake_resp = _make_response(raise_error=True)
    with mock.patch("httpx.post", return_value=fake_resp):
        with pytest.raises(ValueError, match="Failed to update ticket"):
            client.update_ticket_status("1", "closed")


# ---------------------------------------------------------------------------
# Resilience: tenacity retry around HTTP transients (extra credit)
# ---------------------------------------------------------------------------


def _server_error_response() -> mock.MagicMock:
    """Return a fake httpx response that raises a 5xx HTTPStatusError."""
    resp = mock.MagicMock()
    resp.status_code = 503
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "service unavailable", request=mock.MagicMock(), response=resp,
    )
    return resp


def test_get_tickets_retries_transient_5xx_then_succeeds() -> None:
    """Two 5xx responses should retry; the third 200 wins."""
    client = HttpTicketClient("http://tickets.local", board_id=BOARD)

    success = _make_response(
        json_data=[{"id": 7, "title": "Recovered", "state": "open", "body": "x"}],
    )
    fake_get = mock.Mock(
        side_effect=[
            _server_error_response(),
            _server_error_response(),
            success,
        ],
    )
    with mock.patch("httpx.get", fake_get):
        tickets = client.get_tickets(status="open")

    assert len(tickets) == 1
    assert tickets[0].ticket_id == "7"
    assert fake_get.call_count == 3


def test_get_tickets_does_not_retry_4xx() -> None:
    """A 404 should fail immediately — retrying caller mistakes is wasteful."""
    client = HttpTicketClient("http://tickets.local", board_id=BOARD)

    not_found = mock.MagicMock()
    not_found.status_code = 404
    not_found.raise_for_status.side_effect = httpx.HTTPStatusError(
        "not found", request=mock.MagicMock(), response=not_found,
    )
    fake_get = mock.Mock(return_value=not_found)
    with mock.patch("httpx.get", fake_get):
        with pytest.raises(ValueError, match="Failed to fetch tickets"):
            client.get_tickets()
    assert fake_get.call_count == 1


def test_create_ticket_retries_connect_errors() -> None:
    """ConnectError is a transient network failure; should retry."""
    client = HttpTicketClient("http://tickets.local", board_id=BOARD)
    success = _make_response(
        json_data={"id": 9, "title": "T", "state": "open", "body": ""},
    )
    fake_post = mock.Mock(
        side_effect=[httpx.ConnectError("boom"), success],
    )
    with mock.patch("httpx.post", fake_post):
        ticket = client.create_ticket("T", "")
    assert ticket.ticket_id == "9"
    assert fake_post.call_count == 2
