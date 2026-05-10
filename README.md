# Chat Client Service — HW3

HW3 builds on the HW2 chat-vertical foundation by adding an AI assistant with
tool calling, cross-vertical issue-tracker integration, full observability,
and Infrastructure-as-Code deployment to Render.

The system is composed of:

- `chat_client_api` — abstract `ChatClient` contract and DTOs (Chat vertical, shared
  across Teams 4/8/9 via the [Shared-API repo](https://github.com/HarshithKoriRaj/Shared-API)).
- `slack_client_impl` — direct Slack implementation registered via `get_client()`.
- `chat_client_service` — FastAPI deployment unit (chat + AI + issue endpoints,
  telemetry middleware, Prometheus metrics, dashboard).
- `chat_client_service_api_client` — OpenAPI-generated HTTP client for the service.
- `chat_client_adapter` — remote `ChatClient` implementation over the service.
- `ai_client_api` — abstract `AiClient` contract with typed tool definitions.
- `openai_ai_client_impl` — OpenAI-backed implementation supporting function calling.
- `ticket_client_api` — abstract `TicketClient` contract for the issue-tracker vertical.
- `http_ticket_client_impl` — HTTP implementation that talks to the issue-tracker service.

## Team

- Harshith Kori Raj
- Lakshmi Hukunda Raju
- Jahnavi Saladhagu
- Baireddy Devendhar Reddy
- Sai Krishna Kommineni

## Quick Start

```bash
uv sync --all-packages
uv run ruff check .
uv run mypy .
uv run pytest --cov=components --cov-report=term-missing
```

Run the service locally:

```bash
export CHAT_CLIENT_SERVICE_BASE_URL="http://localhost:8000"
export SLACK_CLIENT_ID="your-slack-client-id"
export SLACK_CLIENT_SECRET="your-slack-client-secret"
export SLACK_REDIRECT_URI="http://localhost:8000/auth/callback"
export OPENAI_API_KEY="sk-..."
uv run uvicorn chat_client_service.main:app --reload
```

Use the remote adapter through the original interface:

```python
import chat_client_adapter
from chat_client_api import get_client

client = get_client()
channels = client.list_channels()
```

If `CHAT_CLIENT_SERVICE_SESSION_ID` is not set, the adapter creates a service auth
session, opens the browser to Slack login, waits for the callback to complete, and
then continues through the same `ChatClient` contract.

## HW3 Architecture Overview

### AI Integration

The service exposes `POST /ai/chat`. A natural-language prompt is passed to the
registered `AiClient` (currently `openai_ai_client_impl`) along with typed tool
definitions for chat and issue domain actions:

- `get_channels`, `send_message`, `get_messages` — chat-vertical actions.
- `get_issues`, `create_issue`, `update_issue_status` — cross-vertical actions on
  the issue-tracker integration.

The OpenAI client uses function calling to dispatch tool invocations back to the
registered handlers; consumers code only against `AiClient`, never the OpenAI SDK.

### Cross-Vertical Integration

The service consumes the issue-tracker vertical's published API
(`work_mgmt_client_interface`, owned by Team Diamonds) as a git dependency
declared in `pyproject.toml` — not vendored — and resolves it via `uv sync`
directly from the Diamonds repo:

```toml
[tool.uv.sources]
work-mgmt-client-interface = { git = "https://github.com/shubham739/team-diamonds.git", branch = "HW-3", subdirectory = "components/work_mgmt_client_interface" }
```

A concrete `IssueTrackerClient` implementation is injected via
`register_diamonds_client_factory()` — the same DI pattern as HW1's chat
`register_client()`. The runtime `_build_issue_client()` resolution order is:

1. Registered Diamonds `IssueTrackerClient` (cross-vertical).
2. Jira-style HTTP service (`JIRA_SERVICE_BASE_URL` + `JIRA_SERVICE_ACCESS_TOKEN`).
3. Legacy Trello-style `HttpTicketClient` (`TICKET_SERVICE_BASE_URL`).

All three adapters normalise to the same internal contract so AI tools and HTTP
endpoints never branch — swapping providers is a configuration / DI change, not
a code change.

### Observability

The FastAPI app installs a telemetry middleware that records, per request, both
aggregate counters and labeled per-(route, method, status_class) counters and
latency. Metrics are exposed at:

- `GET /metrics` — JSON snapshot (used by the dashboard).
- `GET /metrics/prometheus` — text exposition with labelled counters/gauges,
  scrapeable by Prometheus / Grafana Cloud.
- `GET /dashboard` — live HTML dashboard auto-refreshed every 5 s.

Domain errors (HTTP 4xx) and infrastructure errors (HTTP 5xx) are tracked
separately so success/failure rate breakdowns distinguish caller mistakes from
service incidents.

## Environment Variables

- `SLACK_BOT_TOKEN`: required only for the direct local `slack_client_impl`.
- `SLACK_CLIENT_ID`: Slack OAuth client ID for the FastAPI service.
- `SLACK_CLIENT_SECRET`: Slack OAuth client secret for the FastAPI service.
- `SLACK_REDIRECT_URI`: OAuth callback URL registered with Slack.
- `SLACK_SCOPES`: optional Slack scopes override for the service.
- `CHAT_CLIENT_SERVICE_BASE_URL`: base URL used by the service and adapter.
- `CHAT_CLIENT_SERVICE_SESSION_ID`: optional existing remote auth session.
- `CHAT_CLIENT_SERVICE_OPEN_BROWSER`: whether the adapter should open the browser automatically.
- `CHAT_CLIENT_SERVICE_AUTH_TIMEOUT_SECONDS`: how long the adapter waits for OAuth completion.
- `CHAT_CLIENT_SERVICE_POLL_INTERVAL_SECONDS`: how often the adapter polls auth status.
- `OPENAI_API_KEY`: OpenAI API key for the AI client (HW3).
- `OPENAI_MODEL`: optional override for the OpenAI model (defaults to `gpt-4o-mini`).
- `JIRA_SERVICE_BASE_URL`: base URL of the Jira service adapter.
- `JIRA_SERVICE_ACCESS_TOKEN`: bearer token for the Jira adapter.
- `TICKET_SERVICE_BASE_URL`: legacy fallback for the previous tracker adapter.
- `TICKET_BOARD_ID`: legacy fallback board identifier.

## Issue Tracker Integration (HW3)

This service speaks the Jira contract first, while keeping the previous tracker
path as a fallback until the Jira team sends live details.

Implemented endpoints:

- `GET /issues?ticket_status=open`: list issues by status.
- `GET /issues/{issue_id}`: fetch one issue by ID.
- `POST /issues`: create an issue.
- `PATCH /issues/{issue_id}/status`: update issue status.
- Legacy aliases remain available on `/tickets` during transition.

The AI endpoint `POST /ai/chat` also exposes issue tools:

- `get_issues`
- `create_issue`
- `update_issue_status`

## Generated Client

The service client is generated from the FastAPI OpenAPI schema with `openapi-python-client`. Regenerate it with:

```bash
uv run python -c "from chat_client_service.main import app; import json, pathlib; pathlib.Path('openapi-chat-client-service.json').write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')"
uv run openapi-python-client generate --path openapi-chat-client-service.json --config openapi-python-client-config.yml --meta uv --output-path components/chat_client_service_api_client --overwrite
```

## Quality Gates

- `ruff` passes with the handwritten codebase (`select = ["ALL"]`).
- `mypy` runs in strict mode.
- `pytest --cov=components` exceeds the `90%` threshold from `pyproject.toml`.
- `mkdocs build --strict` succeeds.

## Deployment

The Chat Client Service is deployed as a public FastAPI web service on **Render**.

### Live Service

- Base URL: https://os-bmaq.onrender.com
- OpenAPI Spec: https://os-bmaq.onrender.com/openapi.json
- Swagger Docs: https://os-bmaq.onrender.com/docs
- Health Check: https://os-bmaq.onrender.com/health
- Telemetry Dashboard: https://os-bmaq.onrender.com/dashboard
- Prometheus Metrics: https://os-bmaq.onrender.com/metrics/prometheus

### Platform Configuration

- Platform: Render (Web Service)
- Branch: `HW3`
- Root Directory: `components/chat_client_service`

Start command:

```bash
uv run uvicorn chat_client_service.main:app --host 0.0.0.0 --port $PORT
```

### Environment Variables

All secrets are stored in Render's Environment tab — none are committed to source
control. The IaC definition (`terraform/main.tf`) declares only non-secret
environment variables; `OPENAI_API_KEY`, `SLACK_CLIENT_SECRET`, the Jira bearer
token, and the legacy ticket credentials are set manually through the Render
dashboard. CircleCI uses a `RENDER_DEPLOY_HOOK_URL` context variable to trigger
deploys without ever touching the secrets themselves.

| Variable | Required | Description |
|---|---|---|
| `SLACK_CLIENT_ID` | yes | Slack App client ID (OAuth & Permissions page) |
| `SLACK_CLIENT_SECRET` | yes | Slack App client secret |
| `SLACK_REDIRECT_URI` | yes | Must exactly match the redirect URL in Slack App settings (`https://os-bmaq.onrender.com/auth/callback`) |
| `CHAT_CLIENT_SERVICE_BASE_URL` | yes | `https://os-bmaq.onrender.com` |
| `OPENAI_API_KEY` | yes | OpenAI API key for the AI client |
| `JIRA_SERVICE_BASE_URL` | optional | Jira service URL (preferred) |
| `JIRA_SERVICE_ACCESS_TOKEN` | optional | Jira bearer token |
| `TICKET_SERVICE_BASE_URL` | optional | Legacy tracker fallback URL |
| `TICKET_BOARD_ID` | optional | Legacy tracker board id |
| `SLACK_SCOPES` | no | Defaults to `chat:write,channels:read,channels:history` |
| `OPENAI_MODEL` | no | Defaults to `gpt-4o-mini` |

### Infrastructure as Code (Terraform)

Render is provisioned declaratively via Terraform under `terraform/`:

```
terraform/
├── main.tf        # render_web_service resource
├── variables.tf   # service name, plan, region, branch, build/start commands
└── outputs.tf     # service_url, service_id
```

Bootstrap a fresh environment from the repo root:

```bash
export RENDER_API_KEY="rnd_..."             # Render API key
export TF_VAR_repo_url="https://github.com/NYU-OSPSD-Team-9/OS"
cd terraform
terraform init
terraform plan
terraform apply
```

Secrets (`SLACK_CLIENT_SECRET`, `OPENAI_API_KEY`, Jira/legacy ticket credentials)
are deliberately omitted from Terraform state and set manually in the Render
dashboard or via the Render API. After `apply`, the public service URL is
emitted as the `service_url` output.

### CI/CD Pipeline

CircleCI is configured in [.circleci/config.yml](.circleci/config.yml). Every
push to `HW3` triggers:

1. `uv sync --all-packages`
2. `ruff check .`
3. `mypy .`
4. `pytest --junitxml=test-results/junit.xml --cov=components` — fails if
   coverage drops below 90%
5. On `main` / `HW3`: a `deploy` job posts to `RENDER_DEPLOY_HOOK_URL` to roll
   out the new revision.

Test results and HTML coverage reports are uploaded as CircleCI artifacts.
