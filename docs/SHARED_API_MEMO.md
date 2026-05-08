# Chat Vertical Shared API — Memo

**Vertical:** Chat (Teams 4, 8, 9)
**Teams:** Team 4 (Telegram), Team 8 (Discord), Team 9 (Slack)
**Date:** April 2026

---

## Purpose

This memo documents the standardised API contract agreed upon by the three chat teams.
All implementations must satisfy this interface exactly so that cross-vertical consumers
can depend on it without platform-specific code.

---

## Shared Repository

The ABC lives at: `https://github.com/HarshithKoriRaj/Shared-API`

Install as a dependency:

```
uv add git+https://github.com/HarshithKoriRaj/Shared-API
```

---

## Data Classes

### `Message`

| Field        | Type  | Notes                                              |
|--------------|-------|----------------------------------------------------|
| `message_id` | `str` | Opaque, implementation-defined (e.g. `"C01:ts"`)  |
| `channel`    | `str` | Channel identifier                                 |
| `text`       | `str` | Message body                                       |
| `sender`     | `str` | User identifier (empty string if not applicable)   |
| `timestamp`  | `str` | Platform timestamp string                          |

### `Channel`

| Field          | Type            | Notes                                          |
|----------------|-----------------|------------------------------------------------|
| `channel_id`   | `str`           | Platform-unique channel identifier             |
| `name`         | `str`           | Human-readable channel name                    |
| `is_private`   | `bool \| None`  | `None` if the platform does not expose this    |
| `channel_type` | `str \| None`   | Platform-specific type (e.g. Telegram group)   |

`is_private` and `channel_type` are both optional so that each platform can populate
only what it natively supports without forcing a mapping.

---

## Abstract Methods

```python
def send_message(self, channel_id: str, text: str) -> Message
```
Send a message to the given channel. Returns the posted message. Raises `ValueError`
on failure.

```python
def get_channels(self) -> list[Channel]
```
Return all channels the bot has access to. Returns an empty list on error.

```python
def get_channel(self, channel_id: str) -> Channel
```
Fetch metadata for a single channel. Raises `ValueError` if not found.

```python
def get_messages(self, channel_id: str, limit: int = 10, cursor: str | None = None) -> list[Message]
```
Fetch recent messages. `cursor` is optional pagination; platforms that do not support
it may ignore it. Returns an empty list on error.

```python
def get_message(self, message_id: str) -> Message
```
Fetch a single message by its opaque `message_id`. Raises `ValueError` if not found.

```python
def delete_message(self, message_id: str) -> None
```
Delete a message by its opaque `message_id`. Raises `ValueError` on failure.

---

## Key Design Decisions

1. **`send_message` returns `Message`, not a status object.** All three platforms can
   return the posted message. Errors raise `ValueError` instead.

2. **`message_id` is opaque.** Each platform encodes it internally (Slack uses
   `"channel_id:timestamp"`, Telegram uses `"chat_id:message_id"`). Callers must
   treat it as an opaque handle and never parse it.

3. **`is_private` and `channel_type` are both optional.** Slack uses `is_private`;
   Telegram uses `channel_type`. Neither team is forced to fabricate a value for a
   concept their platform does not have.

4. **`cursor` in `get_messages` is optional.** Platforms without pagination support
   simply ignore it.

5. **Error handling is consistent.** Methods that can fail raise `ValueError`; methods
   that return collections return an empty list on soft failures.

---

## Team 9 Adaptation Plan

1. Rename `channel` parameter to `channel_id` across the ABC.
2. Remove `SendMessageResponse`; `send_message` now returns `Message`.
3. Update `Channel` dataclass: `is_private: bool | None`, add `channel_type: str | None`.
4. Update `SlackClient` to raise `ValueError` (not return a failure object) on API errors.
5. Update the FastAPI service models and endpoints to reflect the new response shape.
6. Update all unit and integration tests.

---

## Unified Credentials Approach

All three Chat-vertical teams (Telegram, Discord, Slack) follow the same
credentials model so cross-vertical consumers do not have to special-case any
backend.

### Storage rules

1. **Never hardcoded, never committed.** Credentials live only in the platform's
   environment store (Render env tab, AWS SSM, GCP Secret Manager, etc.). The
   IaC definition (`terraform/main.tf` for Team 9) declares only non-secret env
   vars; secret values are set manually through the platform dashboard or via a
   privileged API call.
2. **Env-only at the implementation layer.** Each `*_client_impl` reads its
   provider credentials from a single, namespaced env var
   (`SLACK_BOT_TOKEN`, `TELEGRAM_BOT_TOKEN`, `DISCORD_BOT_TOKEN`). The interface
   package (`chat_client_api`) never sees credentials, never accepts auth
   tokens as parameters, and never imports a provider SDK.
3. **OAuth-bearing services hold tokens server-side.** Where a vertical exposes
   a FastAPI service (Team 9), the service performs the OAuth handshake, stores
   the resulting access token in a server-side session keyed by an opaque
   session ID, and returns only the session ID to clients. Clients authenticate
   via `X-Session-ID`; the access token never crosses the HTTP boundary.
4. **CI deploys via deploy hooks, not secrets.** CircleCI uses the platform's
   deploy hook URL (`RENDER_DEPLOY_HOOK_URL`) to trigger a deploy. The CI job
   does not need access to provider credentials.

### Per-team variables

| Team | Provider | Required env vars |
|------|----------|-------------------|
| 4 (Telegram) | Telegram Bot API | `TELEGRAM_BOT_TOKEN` |
| 8 (Discord) | Discord Bot API | `DISCORD_BOT_TOKEN` |
| 9 (Slack) | Slack OAuth + Bot | `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_REDIRECT_URI`, `SLACK_BOT_TOKEN` (local mode only) |

### AI client credentials

Teams that integrate an AI provider follow the same rule: provider key (e.g.
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) is read from the env in the impl
package's factory and never enters the interface package or the wire format.
