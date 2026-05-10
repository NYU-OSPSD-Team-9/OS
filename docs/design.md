# Design

## Goal

Expose the chat client as a standalone service without forcing consumer code to change.

## Main Decisions

- Keep `ChatClient` as the only business-facing contract.
- Put browser-based Slack OAuth in the FastAPI service.
- Use a generated OpenAPI client instead of handwritten request code for the adapter.
- Let the adapter lazily authenticate so the first real operation can bootstrap the remote session.

## Session Model

The service keeps in-memory auth sessions keyed by service session ID. Each session stores:

- whether OAuth is complete
- the Slack bot token returned by Slack
- the optional Slack team name

This keeps the implementation small enough for the assignment while still supporting a real browser redirect flow.

## Testing Strategy

- Unit tests for DTOs, the Slack client, the service routes, and the adapter.
- Integration test for dependency-injection registration.
- Optional E2E test for real Slack credentials.
