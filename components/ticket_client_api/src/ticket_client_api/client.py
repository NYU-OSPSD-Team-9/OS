"""Shared abstract interface for issue tracker clients.

This ABC is agreed upon by the issue tracker vertical (Teams 1, 3, 7)
and consumed by any team integrating with their systems.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Ticket:
    """A normalised issue tracker ticket.

    Attributes:
        ticket_id: Platform-unique ticket identifier.
        title: Short summary of the issue.
        status: Current status (e.g. ``"open"``, ``"in_progress"``, ``"done"``).
        description: Full description of the issue.

    """

    ticket_id: str
    title: str
    status: str
    description: str


class TicketClient(ABC):
    """Abstract interface for issue tracker backends."""

    @abstractmethod
    def get_tickets(self, status: str = "open") -> list[Ticket]:
        """Return a list of tickets filtered by status.

        Args:
            status: Ticket status to filter by (default ``"open"``).

        Returns:
            List of matching tickets.

        """

    @abstractmethod
    def get_ticket(self, ticket_id: str) -> Ticket:
        """Fetch a single ticket by its ID.

        Args:
            ticket_id: Platform-unique ticket identifier.

        Returns:
            The requested ticket.

        Raises:
            ValueError: If the ticket is not found.

        """

    @abstractmethod
    def create_ticket(self, title: str, description: str) -> Ticket:
        """Create a new ticket.

        Args:
            title: Short summary of the issue.
            description: Full description of the issue.

        Returns:
            The newly created ticket.

        """

    @abstractmethod
    def update_ticket_status(self, ticket_id: str, new_status: str) -> None:
        """Update the status of an existing ticket.

        Args:
            ticket_id: Platform-unique ticket identifier.
            new_status: New status value.

        Raises:
            ValueError: If the ticket is not found.

        """
