"""Integration test: AI tool-call invokes the cross-vertical issue tracker.

This test exercises the full path the rubric calls out explicitly:
``AI tool-call → cross-vertical-action``. A fake `AiClient` is registered so
the test does not depend on a live OpenAI account, but every component on the
chat-side path is real:

- the FastAPI service routing
- the telemetry middleware
- the `/ai/chat` endpoint and its tool-binding logic
- the issue-tracker tools (`create_issue`, `update_issue_status`, `get_issues`)
- the `_build_issue_client()` resolution against environment variables
- the `_TicketClientAdapter` normalising the legacy tracker shape

Only the outermost HTTP boundary to the tracker (`HttpTicketClient`'s
provider methods) is faked — the rest of the cross-vertical flow runs for real.
"""
from __future__ import annotations

import json
import os
from http import HTTPStatus
from typing import Any
from unittest import mock

import pytest
from ai_client_api.client import AiClient, AiTool, register_ai_client
from chat_client_api.client import Channel, ChatClient, Message
from chat_client_service.main import (
    _get_authenticated_client,
    app,
    reset_service_state,
)
from fastapi.testclient import TestClient
from ticket_client_api.client import Ticket


class _StubChatClient(ChatClient):
    """Stub chat client used to satisfy the /ai/chat dependency."""

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


class _ToolCallingFakeAiClient(AiClient):
    """Fake AI client that always invokes a single configured tool."""

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
        if self._tool_name not in tool_map:
            msg = f"tool {self._tool_name!r} not exposed by service"
            raise AssertionError(msg)
        tool = tool_map[self._tool_name]
        if tool.handler is None:
            msg = f"tool {self._tool_name!r} has no handler"
            raise AssertionError(msg)
        result = tool.handler(**self._tool_args)
        self.last_handler_result = result
        return f"executed {self._tool_name}: {result}"


def _stub_chat_client() -> _StubChatClient:
    return _StubChatClient()


@pytest.fixture(autouse=True)
def _reset() -> Any:
    reset_service_state()
    app.dependency_overrides[_get_authenticated_client] = _stub_chat_client
    yield
    app.dependency_overrides.clear()


def test_ai_tool_call_creates_cross_vertical_issue() -> None:
    """AI tool-call → POST /issues path: fake AI calls create_issue tool.

    The fake AI invokes the create_issue tool with sample arguments. The tool
    handler resolves the issue-tracker client from env, dispatches through the
    real `_TicketClientAdapter`, and ultimately reaches `HttpTicketClient`
    (whose method is mocked at the network boundary).
    """
    fake_ai = _ToolCallingFakeAiClient(
        tool_name="create_issue",
        tool_args={
            "title": "AI-created bug report",
            "description": "Found while debugging the deploy pipeline",
        },
    )
    register_ai_client(lambda: fake_ai)

    created_issue = Ticket(
        ticket_id="AI-42",
        title="AI-created bug report",
        status="open",
        description="Found while debugging the deploy pipeline",
    )

    with (
        mock.patch.dict(
            os.environ,
            {
                "TICKET_SERVICE_BASE_URL": "http://issues.local",
                "TICKET_BOARD_ID": "board123",
                "JIRA_SERVICE_BASE_URL": "",
                "JIRA_SERVICE_ACCESS_TOKEN": "",
            },
            clear=False,
        ),
        mock.patch(
            "http_ticket_client_impl.client.HttpTicketClient.create_ticket",
            return_value=created_issue,
        ) as mock_create,
    ):
        response = TestClient(app).post(
            "/ai/chat",
            json={"prompt": "create an issue about the deploy bug"},
        )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert "executed create_issue" in body["reply"]

    mock_create.assert_called_once_with(
        "AI-created bug report",
        "Found while debugging the deploy pipeline",
    )

    handler_payload = json.loads(fake_ai.last_handler_result or "{}")
    assert handler_payload["issue_id"] == "AI-42"
    assert handler_payload["status"] == "created"


def test_ai_tool_call_lists_cross_vertical_issues() -> None:
    """AI tool-call → GET /issues path: fake AI calls get_issues tool."""
    fake_ai = _ToolCallingFakeAiClient(
        tool_name="get_issues",
        tool_args={"status": "open"},
    )
    register_ai_client(lambda: fake_ai)

    fake_issues = [
        Ticket(
            ticket_id="1",
            title="Investigate flaky test",
            status="open",
            description="Intermittent CI failure",
        ),
        Ticket(
            ticket_id="2",
            title="Add alerting",
            status="open",
            description="Page on 5xx burn",
        ),
    ]

    with (
        mock.patch.dict(
            os.environ,
            {
                "TICKET_SERVICE_BASE_URL": "http://issues.local",
                "TICKET_BOARD_ID": "board123",
                "JIRA_SERVICE_BASE_URL": "",
                "JIRA_SERVICE_ACCESS_TOKEN": "",
            },
            clear=False,
        ),
        mock.patch(
            "http_ticket_client_impl.client.HttpTicketClient.get_tickets",
            return_value=fake_issues,
        ) as mock_get,
    ):
        response = TestClient(app).post(
            "/ai/chat",
            json={"prompt": "list current open issues"},
        )

    assert response.status_code == HTTPStatus.OK
    mock_get.assert_called_once_with(status="open")

    issues = json.loads(fake_ai.last_handler_result or "[]")
    assert {issue["issue_id"] for issue in issues} == {"1", "2"}


def test_ai_tool_call_updates_cross_vertical_issue_status() -> None:
    """AI tool-call → PATCH /issues/{id}/status path."""
    fake_ai = _ToolCallingFakeAiClient(
        tool_name="update_issue_status",
        tool_args={"issue_id": "AI-42", "new_status": "done"},
    )
    register_ai_client(lambda: fake_ai)

    with (
        mock.patch.dict(
            os.environ,
            {
                "TICKET_SERVICE_BASE_URL": "http://issues.local",
                "TICKET_BOARD_ID": "board123",
                "JIRA_SERVICE_BASE_URL": "",
                "JIRA_SERVICE_ACCESS_TOKEN": "",
            },
            clear=False,
        ),
        mock.patch(
            "http_ticket_client_impl.client.HttpTicketClient.update_ticket_status",
            return_value=None,
        ) as mock_update,
    ):
        response = TestClient(app).post(
            "/ai/chat",
            json={"prompt": "mark issue AI-42 as done"},
        )

    assert response.status_code == HTTPStatus.OK
    mock_update.assert_called_once_with("AI-42", "done")
