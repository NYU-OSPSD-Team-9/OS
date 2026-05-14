# Design Document -- HW3

HW3 layers three new capabilities onto the HW2 chat-vertical foundation:

1. **AI client integration** -- a provider-agnostic AiClient ABC plus OpenAI and Anthropic Claude implementations that support tool calling against domain actions, demonstrably swappable through the same interface.
2. **Cross-vertical issue-tracker and calendar integration** -- the service consumes two other teams published APIs via dependency injection: Team Diamonds (issue tracker) and Team 12 (Outlook Calendar), both declared as git dependencies in pyproject.toml.
3. **Observability** -- request-level telemetry middleware emits per-route / per-method / per-status counters and latency, exposed via JSON, Prometheus, and a live HTML dashboard.

The HW2 architecture (Chat ABC, Slack implementation, FastAPI service, generated
client, remote adapter) is preserved unchanged; HW3 components plug in alongside it.

## HW3 Components

### ai_client_api
Pure-Python abstract interface (AiClient ABC) with two methods:

- send_message(prompt, context) -- basic completion.
- send_message_with_tools(prompt, tools, context) -- completion with typed
  AiTool definitions. Each AiTool carries name, description, JSON-schema
  parameters, and an optional Python handler callable.

The package also exposes:

- tool_from_function() -- auto-generates an AiTool from a typed Python
  function signature, building the JSON schema from type hints automatically.
- AiTextResponse / AiToolCallResponse -- Pydantic models for validated AI responses.
- AiClientError, AiToolError, AiResponseValidationError, AiProviderError
  -- typed domain exceptions for structured error handling.

The package has zero external dependencies and exposes a register_ai_client() /
get_ai_client() factory mirroring the get_client() pattern from HW1.

### openai_ai_client_impl
Concrete OpenAiClient(AiClient) backed by the OpenAI Python SDK. Tool
definitions are translated into the OpenAI function-calling schema; the
implementation drives a tool-call loop (capped at OPENAI_MAX_TOOL_ROUNDS,
default 5) that executes registered handlers, feeds results back into the model,
and returns the final text. Token usage and estimated USD cost are captured on
every call. Tenacity retries with exponential backoff on transient errors.
The API key is read from OPENAI_API_KEY only -- never hardcoded, never committed.

### anthropic_ai_client_impl
Concrete AnthropicAiClient(AiClient) backed by the Anthropic Python SDK.
Implements the exact same AiClient ABC as openai_ai_client_impl -- fully
swappable through the same register_ai_client() / get_ai_client() factory.
Supports tool calling via Anthropic tool_use API, token usage capture, USD
cost estimation, and tenacity-backed retries. The API key is read from
ANTHROPIC_API_KEY only -- never hardcoded, never committed.

### ticket_client_api
Issue-tracker vertical shared ABC: a TicketClient with get_tickets,
get_ticket, create_ticket, update_ticket_status, and a normalized
Ticket dataclass. Provider-agnostic: no Jira / Trello / Linear types leak.

### http_ticket_client_impl
Implements TicketClient over HTTP using httpx. Suitable for any tracker that
exposes a REST contract matching the shared schema.

## Cross-Vertical Integration

The chat service consumes two other teams published interfaces as pyproject.toml
git dependencies:

```toml
[project]
dependencies = [..., "work-mgmt-client-interface"]

[tool.uv.sources]
chat-client-api = { git = "https://github.com/HarshithKoriRaj/Shared-API" }
work-mgmt-client-interface = { git = "https://github.com/shubham739/team-diamonds.git", branch = "HW-3", subdirectory = "components/work_mgmt_client_interface" }
calendar-client-api = { git = "https://github.com/bk00119/ospsd-outlook-calendar-team12.git", branch = "hw-3", subdirectory = "src/calendar_client_api" }
```

The dependency is **not vendored** — `uv sync` resolves it directly from the
Diamonds repo. A concrete `IssueTrackerClient` is injected via the
`register_diamonds_client_factory()` DI hook (mirroring the HW1
`register_client()` / `get_client()` pattern); swapping between providers
(Diamonds → legacy Trello → Jira HTTP) is transparent to AI tools and HTTP
endpoints.

At runtime, _build_issue_client() resolves the active client in this order:

```

                  +---------------------+
   /issues/*   -> | _build_issue_client |
   /ai/chat    -> |   (resolution       |
                  |    order)           |
                  +--------+-----------+
                           |
       +-------------------+-----------------------+
       v                   v                       v
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

  User -> POST /ai/chat {prompt}
          |
          v
    ai_chat handler
          | build tools list (chat + issue + calendar)
          v
    AiClient.send_message_with_tools
          |   ^
          v   | tool result
    OpenAiClient / AnthropicAiClient (function-calling loop)
          |   |
          v   |
    Tool dispatch -> handler(...)
          |
          +-- chat handlers -> ChatClient (Slack)
          +-- issue handlers -> _build_issue_client() -> TicketClient
          |                                              |
          |                                              +-- HTTP -> external tracker
          +-- calendar handlers -> _build_calendar_client() -> CalendarClient

```

The chat handler binds ChatClient per request via the existing session DI;
the issue handlers resolve the TicketClient lazily from environment so the
cross-vertical dependency stays provider-agnostic.

## Observability Strategy

### Middleware
A FastAPI HTTP middleware records, per request, both aggregate counters and
labeled per-(route_template, method, status_class) counters and latency.
Three status classes are tracked separately:

- ok -- HTTP 2xx / 3xx.
- domain_error -- HTTP 4xx (caller mistakes).
- infra_error -- HTTP 5xx (service incidents).

Splitting domain vs infra errors is essential to avoid alerting on user-driven
4xx noise while still page-able on real outages.

### Endpoints
- GET /metrics -- JSON snapshot (totals + per-route breakdown).
- GET /metrics/prometheus -- text exposition format with labelled series.
- GET /dashboard -- HTML view rendering the JSON snapshot, auto-refreshed every 5s.

### Backend
Render runtime stdout is streamed to the platform log viewer. The Prometheus
endpoint is scrapeable from Grafana Cloud. Grafana Alloy scrapes the endpoint
every 30s and remote-writes to Grafana Cloud Hosted Prometheus with an 11-panel
dashboard. SLO-based alerts are configured in Grafana Cloud.

## Shared Vertical Contract (HW3 Refactor)

The Chat vertical (Teams 4 / 8 / 9) agreed on a unified ChatClient ABC and
shared dataclasses (Message, Channel). The contract lives in Shared-API and
is consumed via pyproject.toml git source.

### Team 9 adaptation plan

1. Replace the local chat_client_api package with the shared one from Shared-API.
2. Rename channel to channel_id on every ChatClient method.
3. Drop SendMessageResponse DTO; have send_message return a Message directly.
4. Update the Channel dataclass to add is_private and channel_type fields.
5. Make SlackClient raise ValueError on API errors instead of returning failure objects.
6. Update chat_client_service models and routes for the new DTO shapes.
7. Update chat_client_adapter to map the regenerated client responses.
8. Update all unit / integration / E2E tests for the new field names.

The full memo is in docs/SHARED_API_MEMO.md.

## Key Design Decisions (HW3)

### AI client interface mirrors the HW1 chat-client pattern
Same register_X / get_X factory shape so the service has a single mental
model for dependency injection across verticals.

### Multi-provider AI -- swappable through the same interface
Both openai_ai_client_impl and anthropic_ai_client_impl implement the same
AiClient ABC. Switching providers is a single register_ai_client() call --
no changes to tool definitions, route handlers, or tests.

### Structured AI outputs
tool_from_function() auto-generates JSON schemas from Python type hints.
AI responses are validated via Pydantic models (AiTextResponse, AiToolCallResponse).
Failures raise typed domain exceptions (AiToolError, AiResponseValidationError,
AiProviderError).

### Tool handlers close over per-request state
Chat tools close over the request authenticated ChatClient so each AI call
acts on behalf of the right Slack workspace; issue tools resolve the
TicketClient lazily so swapping Jira vs legacy is purely env-driven.

### Tool round cap
The loop is capped at OPENAI_MAX_TOOL_ROUNDS (default 5, env-tunable) to
bound runaway recursion if the model hallucinates an endless tool chain.

### Resilience patterns
Both AI clients and the HTTP ticket client use tenacity retries with exponential
backoff on transient errors. 4xx caller mistakes are not retried.

### Telemetry stays in-process
State is held under a threading.Lock for atomic updates. The Prometheus endpoint
forwards to Grafana Cloud.

### Domain vs infrastructure error split
HW3 separates 4xx and 5xx so dashboards and alerts can target real incidents.

## Multi-Environment IaC

Separate staging and production Terraform variable files:

- terraform/environments/stg/terraform.tfvars -- HW3-final branch, gpt-4o-mini
- terraform/environments/prod/terraform.tfvars -- main branch, gpt-4o

Promotion path: HW3-final -> CI green -> peer review -> main (production).

## HW2 Architecture (carried forward)

The HW2 design (chat_client_api, slack_client_impl, chat_client_service,
chat_client_service_api_client, chat_client_adapter, OAuth flow,
in-memory session store, lazy adapter authentication) remains valid.

## Tradeoffs and Known Limitations

| Area | Decision | Limitation |
|------|----------|------------|
| Session persistence | In-memory dict | Lost on restart; not production-grade |
| Token storage | Session memory only | Not encrypted at rest |
| Telemetry storage | Process memory | Lost on redeploy; intentional for demo scope |
| AI tool loop | Sequential rounds | No parallel tool execution |
| AI provider | OpenAI + Anthropic Claude | Swappable via register_ai_client() factory |
| Issue tracker | Three providers wired | Live cutover depends on Jira team handoff |
| Concurrency | threading.Lock on metrics | Session race conditions possible at high load |
