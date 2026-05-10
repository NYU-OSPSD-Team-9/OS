"""HTTP adapter for Team 3's Trello-based issue tracker service.

Calls Team 3 (ospsd-team-03) via their REST API at
``/boards/{board}/issues`` and maps their response schema to the
shared ``Ticket`` data class used by the ticket_client_api contract.

Transient connection / 5xx errors are retried with exponential backoff via
tenacity. Domain (4xx) responses are NOT retried — those signal a caller
error that another attempt cannot fix.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)
from ticket_client_api.client import Ticket, TicketClient

if TYPE_CHECKING:
    from collections.abc import Callable

_MAX_RETRY_ATTEMPTS = 3
_RETRY_INITIAL_WAIT_SECONDS = 0.5
_RETRY_MAX_WAIT_SECONDS = 4
_HTTP_SERVER_ERROR_FLOOR = 500


def _is_transient_http_error(exc: BaseException) -> bool:
    """Return True if the error is worth retrying.

    Connection / read / write / timeout errors are always transient. HTTP
    status errors are transient only when the response is 5xx — 4xx means
    the caller is wrong and retrying will not help.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= _HTTP_SERVER_ERROR_FLOOR
    return isinstance(exc, httpx.HTTPError)


def _with_retries(func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a function with retry-on-transient-HTTP-error and exponential backoff."""
    return retry(
        reraise=True,
        stop=stop_after_attempt(_MAX_RETRY_ATTEMPTS),
        wait=wait_exponential(
            multiplier=_RETRY_INITIAL_WAIT_SECONDS,
            max=_RETRY_MAX_WAIT_SECONDS,
        ),
        retry=retry_if_exception(_is_transient_http_error),
    )(func)


def _ticket_from_issue(data: dict[str, object]) -> Ticket:
    """Build a Ticket from Team 3's ``IssueOut`` JSON shape.

    Team 3 returns ``{"id": int, "title": str, "body": str, "state": str}``.
    We map ``id → ticket_id``, ``body → description``, ``state → status``.
    """
    return Ticket(
        ticket_id=str(data["id"]),
        title=str(data["title"]),
        status=str(data["state"]),
        description=str(data.get("body", "")),
    )


class HttpTicketClient(TicketClient):
    """Calls Team 3's issue tracker service over HTTP."""

    def __init__(self, base_url: str, board_id: str = "") -> None:
        """Initialise with the service base URL and Trello board ID.

        Args:
            base_url: Base URL of Team 3's service
                      (e.g. ``"https://issue-tracker-service-793028870171.us-central1.run.app"``).
            board_id: Trello board ID to query.

        """
        self._base_url = base_url.rstrip("/")
        self._board_id = board_id

    @_with_retries
    def _get(self, url: str) -> httpx.Response:
        response = httpx.get(url, timeout=15.0)
        response.raise_for_status()
        return response

    @_with_retries
    def _post(
        self,
        url: str,
        *,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        response = httpx.post(url, json=json, timeout=15.0)
        response.raise_for_status()
        return response

    def get_tickets(self, status: str = "open") -> list[Ticket]:
        """Fetch issues from the board, optionally filtered by state.

        Args:
            status: Issue state filter (applied client-side).

        Returns:
            List of tickets.

        Raises:
            ValueError: On HTTP error.

        """
        try:
            response = self._get(
                f"{self._base_url}/boards/{self._board_id}/issues",
            )
        except httpx.HTTPError as exc:
            msg = f"Failed to fetch tickets: {exc}"
            raise ValueError(msg) from exc

        issues: list[dict[str, object]] = response.json()
        tickets = [_ticket_from_issue(i) for i in issues]
        if status:
            tickets = [t for t in tickets if t.status == status]
        return tickets

    def get_ticket(self, ticket_id: str) -> Ticket:
        """Fetch a single issue by ID.

        Args:
            ticket_id: Issue identifier (numeric string).

        Returns:
            The requested ticket.

        Raises:
            ValueError: If not found or on HTTP error.

        """
        try:
            response = self._get(
                f"{self._base_url}/boards/{self._board_id}/issues/{ticket_id}",
            )
        except httpx.HTTPError as exc:
            msg = f"Ticket not found: {ticket_id}"
            raise ValueError(msg) from exc
        return _ticket_from_issue(response.json())

    def create_ticket(self, title: str, description: str) -> Ticket:
        """Create a new issue on the board.

        Args:
            title: Issue title.
            description: Issue body text.

        Returns:
            The created ticket.

        Raises:
            ValueError: On HTTP error.

        """
        try:
            response = self._post(
                f"{self._base_url}/boards/{self._board_id}/issues",
                json={"title": title, "body": description},
            )
        except httpx.HTTPError as exc:
            msg = f"Failed to create ticket: {exc}"
            raise ValueError(msg) from exc
        return _ticket_from_issue(response.json())

    def update_ticket_status(
        self,
        ticket_id: str,
        new_status: str,
    ) -> None:
        """Update issue status. Only 'closed' is supported by Team 3's API.

        Args:
            ticket_id: Issue identifier.
            new_status: Target status. Only 'closed' is supported.

        Raises:
            ValueError: If new_status is not 'closed' or on HTTP error.

        """
        if new_status != "closed":
            msg = (
                f"Unsupported status '{new_status}'. "
                "Team 3's API only supports 'closed'."
            )
            raise ValueError(msg)
        try:
            self._post(
                f"{self._base_url}/boards/{self._board_id}"
                f"/issues/{ticket_id}/close",
            )
        except httpx.HTTPError as exc:
            msg = f"Failed to update ticket {ticket_id}: {exc}"
            raise ValueError(msg) from exc
