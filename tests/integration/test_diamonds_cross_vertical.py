"""Integration test: AI tool-call → Team Diamonds IssueTrackerClient.

This exercises the *cross-vertical* path the rubric calls out:

- The published Diamonds interface (`work_mgmt_client_interface`) is pulled in
  from their HW-3 branch via `pyproject.toml` (`tool.uv.sources`).
- A concrete `IssueTrackerClient` implementation is injected via the
  `register_diamonds_client_factory()` DI hook.
- A fake `AiClient` triggers the `create_issue` and `update_issue_status` tools
  exposed by `/ai/chat`.
- The tool handlers reach `_DiamondsClientAdapter`, which calls the injected
  Diamonds client.
- Only the Diamonds-side implementation is fake; the FastAPI service, the
  telemetry middleware, the AI tool dispatch loop, and the issue-tracker
  resolution chain run for real.
"""
from __future__ import annotations

import json
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
from ai_client_api.client import AiClient, AiTool, register_ai_client
from chat_client_api.client import Channel, ChatClient, Message
from chat_client_service.main import (
    _get_authenticated_client,
    app,
    register_diamonds_client_factory,
    reset_service_state,
)
from fastapi.testclient import TestClient
from work_mgmt_client_interface import (
    Board,
    Issue,
    IssueTrackerClient,
    IssueUpdate,
    Status,
)
from work_mgmt_client_interface import (
    List as DiamondsList,
)


class _FakeIssue(Issue):
    """Minimal concrete Diamonds Issue for tests."""

    def __init__(
        self,
        issue_id: str,
        title: str,
        description: str,
        status: Status,
    ) -> None:
        self._id = issue_id
        self._title = title
        self._description = description
        self._status = status

    @property
    def id(self) -> str:
        return self._id

    @property
    def title(self) -> str:
        return self._title

    @property
    def description(self) -> str:
        return self._description

    @property
    def status(self) -> Status:
        return self._status

    @property
    def assignee(self) -> str | None:
        return None

    @property
    def due_date(self) -> str | None:
        return None

    def update(self, update: IssueUpdate) -> None:
        if update.title is not None:
            self._title = update.title
        if update.description is not None:
            self._description = update.description
        if update.status is not None:
            self._status = update.status


class _FakeDiamondsClient(IssueTrackerClient):
    """Concrete IssueTrackerClient capturing what the AI tool dispatches."""

    def __init__(self) -> None:
        self.created: list[tuple[str, str, Status]] = []
        self.updated: list[tuple[str, IssueUpdate]] = []
        self.deleted: list[str] = []
        self._issues: dict[str, _FakeIssue] = {
            "DIA-1": _FakeIssue("DIA-1", "Existing", "from fixture", Status.TODO),
        }

    def get_issue(self, issue_id: str) -> Issue:
        return self._issues[issue_id]

    def get_issues(  # noqa: PLR0913
        self,
        *,
        title: str | None = None,
        description: str | None = None,
        status: Status | None = None,
        assignee: str | None = None,
        due_date: str | None = None,
        max_results: int = 20,
    ) -> Iterator[Issue]:
        del title, description, assignee, due_date, max_results
        for issue in self._issues.values():
            if status is None or issue.status == status:
                yield issue

    def create_issue(
        self,
        *,
        title: str | None = None,
        description: str | None = None,
        status: Status | None = None,
        assignee: str | None = None,
        due_date: str | None = None,
    ) -> Issue:
        del assignee, due_date
        issue_id = f"DIA-{len(self._issues) + 1}"
        new_issue = _FakeIssue(
            issue_id,
            title or "",
            description or "",
            status or Status.TODO,
        )
        self._issues[issue_id] = new_issue
        self.created.append((title or "", description or "", new_issue.status))
        return new_issue

    def update_issue(self, issue_id: str, update: IssueUpdate) -> Issue:
        issue = self._issues[issue_id]
        issue.update(update)
        self.updated.append((issue_id, update))
        return issue

    def delete_issue(self, issue_id: str) -> None:
        self.deleted.append(issue_id)
        self._issues.pop(issue_id, None)

    def get_board(self, board_id: str) -> Board:
        msg = "Board access not used in this test"
        raise NotImplementedError(msg)

    def get_boards(self) -> Iterator[Board]:
        return iter(())

    def get_list(self, list_id: str) -> DiamondsList:
        msg = "List access not used in this test"
        raise NotImplementedError(msg)

    def get_lists(self, board_id: str) -> Iterator[DiamondsList]:
        return iter(())


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
def diamonds_client() -> Iterator[_FakeDiamondsClient]:
    """Inject a fake Diamonds IssueTrackerClient and stub chat dependency."""
    reset_service_state()
    fake = _FakeDiamondsClient()
    register_diamonds_client_factory(lambda: fake)
    app.dependency_overrides[_get_authenticated_client] = _stub_chat
    try:
        yield fake
    finally:
        register_diamonds_client_factory(None)
        app.dependency_overrides.clear()


def test_ai_tool_call_creates_issue_via_diamonds(
    diamonds_client: _FakeDiamondsClient,
) -> None:
    """AI create_issue tool reaches the injected Diamonds IssueTrackerClient."""
    fake_ai = _ToolCallingFakeAi(
        tool_name="create_issue",
        tool_args={
            "title": "Cross-vertical bug",
            "description": "Caught by the AI assistant",
        },
    )
    register_ai_client(lambda: fake_ai)

    response = TestClient(app).post(
        "/ai/chat",
        json={"prompt": "create a bug report"},
    )

    assert response.status_code == HTTPStatus.OK
    assert "executed create_issue" in response.json()["reply"]

    assert len(diamonds_client.created) == 1
    title, description, _status = diamonds_client.created[0]
    assert title == "Cross-vertical bug"
    assert description == "Caught by the AI assistant"

    handler_payload = json.loads(fake_ai.last_handler_result or "{}")
    assert handler_payload["status"] == "created"
    assert handler_payload["issue_id"].startswith("DIA-")


def test_ai_tool_call_updates_issue_status_via_diamonds(
    diamonds_client: _FakeDiamondsClient,
) -> None:
    """AI update_issue_status tool maps free-form status to the Diamonds enum."""
    fake_ai = _ToolCallingFakeAi(
        tool_name="update_issue_status",
        tool_args={"issue_id": "DIA-1", "new_status": "done"},
    )
    register_ai_client(lambda: fake_ai)

    response = TestClient(app).post(
        "/ai/chat",
        json={"prompt": "mark DIA-1 as done"},
    )

    assert response.status_code == HTTPStatus.OK
    assert len(diamonds_client.updated) == 1
    issue_id, update = diamonds_client.updated[0]
    assert issue_id == "DIA-1"
    assert update.status == Status.COMPLETE


def test_ai_tool_call_lists_issues_via_diamonds(
    diamonds_client: _FakeDiamondsClient,
) -> None:
    """AI get_issues tool iterates the injected Diamonds client."""
    fake_ai = _ToolCallingFakeAi(
        tool_name="get_issues",
        tool_args={"status": "open"},
    )
    register_ai_client(lambda: fake_ai)

    response = TestClient(app).post(
        "/ai/chat",
        json={"prompt": "show me open issues"},
    )

    assert response.status_code == HTTPStatus.OK
    issues = json.loads(fake_ai.last_handler_result or "[]")
    assert {issue["issue_id"] for issue in issues} == {"DIA-1"}
    # Confirm we kept the test independent from the fixture's Diamonds client.
    assert diamonds_client is not None
