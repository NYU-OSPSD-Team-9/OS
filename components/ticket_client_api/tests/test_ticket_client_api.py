"""Unit tests for the ticket client ABC."""
from __future__ import annotations

from ticket_client_api.client import Ticket, TicketClient


class _MockTicketClient(TicketClient):
    """Minimal concrete implementation for testing the ABC contract."""

    def get_tickets(self, status: str = "open") -> list[Ticket]:
        return [Ticket(ticket_id="T1", title="Bug", status=status, description="desc")]

    def get_ticket(self, ticket_id: str) -> Ticket:
        return Ticket(
            ticket_id=ticket_id, title="Bug", status="open", description="desc",
        )

    def create_ticket(self, title: str, description: str) -> Ticket:
        return Ticket(
            ticket_id="T2", title=title, status="open", description=description,
        )

    def update_ticket_status(self, ticket_id: str, new_status: str) -> None:
        pass


def test_ticket_dataclass_fields() -> None:
    """Ticket dataclass should expose required fields."""
    t = Ticket(ticket_id="T1", title="Fix bug", status="open", description="details")
    assert t.ticket_id == "T1"
    assert t.title == "Fix bug"
    assert t.status == "open"
    assert t.description == "details"


def test_get_tickets_returns_list() -> None:
    """get_tickets should return a list of Ticket objects."""
    client = _MockTicketClient()
    tickets = client.get_tickets()
    assert len(tickets) == 1
    assert isinstance(tickets[0], Ticket)


def test_get_ticket_returns_single_ticket() -> None:
    """get_ticket should return a single Ticket."""
    client = _MockTicketClient()
    ticket = client.get_ticket("T1")
    assert ticket.ticket_id == "T1"


def test_create_ticket_returns_ticket() -> None:
    """create_ticket should return the created Ticket."""
    client = _MockTicketClient()
    ticket = client.create_ticket("New feature", "Implement X")
    assert ticket.title == "New feature"


def test_update_ticket_status_does_not_raise() -> None:
    """update_ticket_status should complete without error."""
    client = _MockTicketClient()
    client.update_ticket_status("T1", "done")
