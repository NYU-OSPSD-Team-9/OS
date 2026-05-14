"""Integration tests verifying cross-vertical issue integration.

Team 9 (Slack/Chat) integrates with the issue tracker vertical
(Teams 1, 3, 7) via the shared issue API contract and an HTTP adapter.
These tests verify that the issue endpoints are wired correctly without
requiring a live Jira service.
"""
from __future__ import annotations

import os
from http import HTTPStatus
from unittest import mock

import pytest
from chat_client_service.main import app, reset_service_state
from fastapi.testclient import TestClient
from ticket_client_api.client import Ticket


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_service_state()


def test_list_issues_without_env_returns_503() -> None:
    """GET /issues should return 503 when JIRA_SERVICE_BASE_URL is not set."""
    with mock.patch.dict(
        os.environ,
        {"JIRA_SERVICE_BASE_URL": ""},
        clear=True,
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/issues")
    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE


def test_list_issues_success() -> None:
    """GET /issues should return issues from the Jira service path."""
    fake_issues = [
        Ticket(
            ticket_id="1",
            title="Fix login bug",
            status="open",
            description="Login fails",
        ),
        Ticket(
            ticket_id="2",
            title="Add dark mode",
            status="open",
            description="Feature request",
        ),
    ]
    with (
        mock.patch.dict(
            os.environ,
            {
                "TICKET_SERVICE_BASE_URL": "http://issues.local",
                "TICKET_BOARD_ID": "board123",
            },
            clear=False,
        ),
        mock.patch(
            "http_ticket_client_impl.client.HttpTicketClient.get_tickets",
            return_value=fake_issues,
        ),
    ):
        client = TestClient(app)
        response = client.get("/issues")

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert len(data["issues"]) == len(fake_issues)
    assert data["issues"][0]["issue_id"] == "1"
    assert data["issues"][1]["title"] == "Add dark mode"


def test_list_issues_with_status_filter() -> None:
    """GET /issues?ticket_status=done should pass status to the issue client."""
    fake_issues: list[Ticket] = []
    with (
        mock.patch.dict(
            os.environ,
            {
                "TICKET_SERVICE_BASE_URL": "http://issues.local",
                "TICKET_BOARD_ID": "board123",
            },
            clear=False,
        ),
        mock.patch(
            "http_ticket_client_impl.client.HttpTicketClient.get_tickets",
            return_value=fake_issues,
        ) as mock_get,
    ):
        client = TestClient(app)
        client.get("/issues?ticket_status=done")

    mock_get.assert_called_once_with(status="done")


def test_list_issues_service_error_returns_502() -> None:
    """GET /issues should return 502 when the Jira service is unreachable."""
    with (
        mock.patch.dict(
            os.environ,
            {
                "TICKET_SERVICE_BASE_URL": "http://issues.local",
                "TICKET_BOARD_ID": "board123",
            },
            clear=False,
        ),
        mock.patch(
            "http_ticket_client_impl.client.HttpTicketClient.get_tickets",
            side_effect=ValueError(
                "Failed to fetch issues: connection refused",
            ),
        ),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/issues")

    assert response.status_code == HTTPStatus.BAD_GATEWAY


def test_get_issue_success() -> None:
    """GET /issues/{issue_id} should return a single issue."""
    fake_issue = Ticket(
        ticket_id="77",
        title="Investigate flaky test",
        status="open",
        description="Intermittent CI failure",
    )
    with (
        mock.patch.dict(
            os.environ,
            {
                "TICKET_SERVICE_BASE_URL": "http://issues.local",
                "TICKET_BOARD_ID": "board123",
            },
            clear=False,
        ),
        mock.patch(
            "http_ticket_client_impl.client.HttpTicketClient.get_ticket",
            return_value=fake_issue,
        ),
    ):
        client = TestClient(app)
        response = client.get("/issues/77")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["issue"]["issue_id"] == "77"


def test_create_issue_success() -> None:
    """POST /issues should create and return an issue."""
    fake_issue = Ticket(
        ticket_id="88",
        title="Add alerting",
        status="open",
        description="Add alerting for 5xx rates",
    )
    with (
        mock.patch.dict(
            os.environ,
            {
                "TICKET_SERVICE_BASE_URL": "http://issues.local",
                "TICKET_BOARD_ID": "board123",
            },
            clear=False,
        ),
        mock.patch(
            "http_ticket_client_impl.client.HttpTicketClient.create_ticket",
            return_value=fake_issue,
        ) as mock_create,
    ):
        client = TestClient(app)
        response = client.post(
            "/issues",
            json={
                "title": "Add alerting",
                "description": "Add alerting for 5xx rates",
            },
        )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["issue"]["issue_id"] == "88"
    mock_create.assert_called_once_with(
        "Add alerting",
        "Add alerting for 5xx rates",
    )


def test_update_issue_status_success() -> None:
    """PATCH /issues/{issue_id}/status should update issue status."""
    with (
        mock.patch.dict(
            os.environ,
            {
                "TICKET_SERVICE_BASE_URL": "http://issues.local",
                "TICKET_BOARD_ID": "board123",
            },
            clear=False,
        ),
        mock.patch(
            "http_ticket_client_impl.client.HttpTicketClient.update_ticket_status",
            return_value=None,
        ) as mock_update,
    ):
        client = TestClient(app)
        response = client.patch(
            "/issues/88/status",
            json={"new_status": "done"},
        )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok", "issue_id": "88"}
    mock_update.assert_called_once()
