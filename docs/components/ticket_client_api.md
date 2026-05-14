# Ticket Client API

Abstract interface for issue tracker integrations.

## Overview

The `ticket_client_api` package defines the provider-agnostic `TicketClient` ABC with a normalized `Ticket` dataclass.

## Methods

- `get_tickets(status)` — list tickets by status.
- `get_ticket(ticket_id)` — fetch one ticket.
- `create_ticket(title, description)` — create a ticket.
- `update_ticket_status(ticket_id, new_status)` — update ticket status.
