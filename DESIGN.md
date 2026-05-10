# Design Document — HW3

HW3 layers three new capabilities onto the HW2 chat-vertical foundation:

1. **AI client integration** — a provider-agnostic `AiClient` ABC plus an OpenAI
   implementation that supports tool calling against domain actions.
2. **Cross-vertical issue-tracker integration** — the service consumes the issue
   tracker vertical's `TicketClient` contract via dependency injection, with two
   swappable implementations (Jira-style HTTP service and legacy Trello-style
   service).
3. **Observability** — request-level telemetry middleware emits per-route /
   per-method / per-status counters and latency, exposed via JSON, Prometheus,
   and a live HTML dashboard.

The HW2 architecture (Chat ABC, Slack implementation, FastAPI service, generated
client, remote adapter) is preserved unchanged; HW3 components plug in alongside
it.

## HW3 Components

### `ai_client_api`
Pure-Python abstract interface (`AiClient` ABC) with two methods:

- `send_message(prompt, context)` — basic completion.
- `send_message_with_tools(prompt, tools, context)` — completion with typed
  `AiTool` definitions. Each `AiTool` carries `name`, `description`, JSON-schema
  `parameters`, and an optional Python `handler` callable.

The package has zero external dependencies (no provider SDKs, no HTTP libraries)
and exposes a `register_ai_client()` / `get_ai_client()` factory mirroring the
`get_client()` pattern from HW1.

### `openai_ai_client_impl`
Concrete `OpenAiClient(AiClient)` backed by the OpenAI Python SDK. Tool
definitions are translated into the OpenAI function-calling schema; the
implementation drives a tool-call loop (capped at 5 rounds) that executes
registered handlers, feeds results back into the model, and returns the final
text. Importing the package self-registers it via `register_ai_client()`. The
API key is read from `OPENAI_API_KEY` only — never hardcoded, never committed.

### `ticket_client_api`
Issue-tracker vertical's shared ABC: a `TicketClient` with `get_tickets`,
`get_ticket`, `create_ticket`, `update_ticket_status`, and a normalized
`Ticket` dataclass. Provider-agnostic: no Jira / Trello / Linear types leak.

### `http_ticket_client_impl`
Implements `TicketClient` over HTTP using `httpx`. Suitable for any tracker that
exposes a REST contract matching the shared schema.

## Cross-Vertical Integration

The chat service consumes the issue-tracker vertical's published interface
(`work_mgmt_client_interface`, owned by Team Diamonds) as a `pyproject.toml`
git dependency:

```toml
[project]
dependencies = [..., "work-mgmt-client-interface"]

[tool.uv.sources]
work-mgmt-client-interface = { git = "https://github.com/shubham739/team-diamonds.git", branch = "HW-3", subdirectory = "components/work_mgmt_client_interface" }
```

The dependency is **not vendored** — `uv sync` resolves it directly from the
Diamonds repo. A concrete `IssueTrackerClient` is injected via the
`register_diamonds_client_factory()` DI hook (mirroring the HW1
`register_client()` / `get_client()` pattern); swapping between providers
(Diamonds → legacy Trello → Jira HTTP) is transparent to AI tools and HTTP
endpoints.

At runtime, `_build_issue_client()` resolves the active client in this order:

```
                  ┌─────────────────────┐
   /issues/*   ─▶ │ _build_issue_client │
   /ai/chat    ─▶ │   (resolution       │
                  │    order)           │
                  └────────┬────────────┘
                           │
       ┌───────────────────┼─────────────────────┐
       ▼                   ▼                     ▼
 _DiamondsClientAdapter  Jira HTTP        HttpTicketClient (legacy)
 (work_mgmt_client_       (JIRA_SERVICE_   (TICKET_SERVICE_BASE_URL +
  interface, injected)     BASE_URL +       TICKET_BOARD_ID)
                           JIRA_SERVICE_
                           ACCESS_TOKEN)
```

All three branches conform to the same internal adapter shape so AI tools and
HTTP route handlers do not branch. Swapping providers is a configuration /
DI change, not a code change.

## AI Integration Flow

```
User → POST /ai/chat {prompt}
        │
        ▼
  ai_chat handler
        │ build tools list (chat + issue)
        ▼
  AiClient.send_message_with_tools
        │   ▲
        ▼   │ tool result
  OpenAiClient (function-calling loop)
        │   │
        ▼   │
  Tool dispatch → handler(...)
        │
        ├── chat handlers → ChatClient (Slack)
        └── issue handlers → _build_issue_client() → TicketClient
                                                     │
                                                     └── HTTP → external tracker
```

The chat handler binds `ChatClient` per request via the existing session DI;
the issue handlers resolve the `TicketClient` lazily from environment so the
cross-vertical dependency stays provider-agnostic.

## Observability Strategy

### Middleware
A FastAPI HTTP middleware records, per request, both aggregate counters and
labeled per-`(route_template, method, status_class)` counters and latency. Three
status classes are tracked separately:

- `ok` — HTTP 2xx / 3xx.
- `domain_error` — HTTP 4xx (caller mistakes).
- `infra_error` — HTTP 5xx (service incidents).

Splitting domain vs infra errors is essential to avoid alerting on user-driven
4xx noise while still page-able on real outages.

### Endpoints
- `GET /metrics` — JSON snapshot (totals + per-route breakdown).
- `GET /metrics/prometheus` — text exposition format with labelled series:

  ```
  chat_requests_by_route_total{route="/issues",method="GET",status_class="ok"} 12
  chat_request_latency_ms_sum{route="/issues",method="GET"} 423.7
  chat_request_latency_ms_count{route="/issues",method="GET"} 12
  ```

- `GET /dashboard` — HTML view rendering the JSON snapshot, auto-refreshed
  every 5 s.

### Backend
Render's runtime stdout is streamed to the platform's log viewer. The Prometheus
endpoint is scrapeable from Grafana Cloud / Prometheus / any metrics agent that
speaks the OpenMetrics text format. The dashboard runs in-process for the demo
video.

## Shared Vertical Contract (HW3 Refactor)

The Chat vertical (Teams 4 / 8 / 9) agreed on a unified `ChatClient` ABC and
shared dataclasses (`Message`, `Channel`). The contract lives in
[`Shared-API`](https://github.com/HarshithKoriRaj/Shared-API) and is consumed
via `pyproject.toml`:

```toml
[tool.uv.sources]
chat-client-api = { git = "https://github.com/HarshithKoriRaj/Shared-API" }
```

### Team 9 adaptation plan

Team 9's HW2 codebase had a custom `ChatClient` ABC and a Slack-shaped DTO
that didn't match the agreed Chat-vertical contract. The plan to converge,
in dependency order, was:

1. **Replace the local `chat_client_api` package** with the shared one
   pulled from the `Shared-API` git source. Drop our private copy entirely
   so there is one source of truth for the ABC and DTOs.
2. **Rename `channel` → `channel_id`** on every `ChatClient` method so the
   parameter name matches the agreed contract. *Breaking change for every
   call site.*
3. **Drop our `SendMessageResponse` DTO**; have `send_message` return a
   `Message` directly per the contract. *Breaking change in
   `chat_client_service`'s `/messages` route, in the generated OpenAPI
   client, in `chat_client_adapter`, and in every unit test that asserted
   on the old shape.*
4. **Update the `Channel` dataclass** to add `is_private: bool | None`
   and `channel_type: str | None` (both optional so platforms that don't
   model the concept can leave them `None`).
5. **Make `SlackClient` raise `ValueError` on API errors** instead of
   returning a failure object. *Breaking change for any caller that was
   inspecting return values for failure; replaced by `try/except`.*
6. **Update `chat_client_service` models and routes** so the FastAPI
   responses serialise the new DTO shapes; regenerate
   `chat_client_service_api_client` from the new OpenAPI spec.
7. **Update `chat_client_adapter`** to map the regenerated client's
   responses back to the new DTOs.
8. **Update all unit / integration / E2E tests** to assert on the new
   field names and exception-based error semantics.

The full memo (purpose, agreed contract, unified credentials approach) is
in `docs/SHARED_API_MEMO.md`.

## Key Design Decisions (HW3)

### AI client interface mirrors the HW1 chat-client pattern
Same `register_X` / `get_X` factory shape so the service has a single mental
model for dependency injection across verticals.

### Tool handlers close over per-request state
Chat tools close over the request's authenticated `ChatClient` so each AI call
acts on behalf of the right Slack workspace; issue tools resolve the
`TicketClient` lazily so swapping Jira ↔ legacy is purely env-driven.

### Tool round cap
The OpenAI loop is capped at 5 tool rounds to bound runaway recursion if the
model hallucinates an endless tool chain.

### Telemetry stays in-process
A heavyweight metrics agent isn't justified at this scope; the Prometheus
endpoint is sufficient to forward to a real backend, and the HTML dashboard is a
zero-dep view for the demo. State is held under a `threading.Lock` for atomic
updates.

### Domain vs infrastructure error split
Counting only `status >= 400` collapses 422 (caller mistake) and 503 (service
outage). HW3 separates the two so dashboards/alerts can target real incidents.

## HW2 Architecture (carried forward)

The HW2 design (`chat_client_api`, `slack_client_impl`, `chat_client_service`,
`chat_client_service_api_client`, `chat_client_adapter`, OAuth flow,
in-memory session store, lazy adapter authentication) remains valid and is not
re-described here. See git history at the `Hw2` branch tag and the
`docs/hw2_traceability.md` page for the full HW2 mapping.

## Tradeoffs and Known Limitations

| Area | Decision | Limitation |
|------|----------|------------|
| Session persistence | In-memory dict | Lost on restart; not production-grade |
| Token storage | Session memory only | Not encrypted at rest |
| Telemetry storage | Process memory | Lost on redeploy; intentional for demo scope |
| AI tool loop | Sequential rounds | No parallel tool execution |
| AI provider | Single (OpenAI) | Multi-provider swap is left as extra credit |
| Issue tracker | Two providers wired | Live cutover depends on Jira team handoff |
| Concurrency | `threading.Lock` on metrics; no lock on session store | Session race conditions possible at high load |
