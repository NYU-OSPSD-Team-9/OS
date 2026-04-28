# Chat Client Service

HW2 implements a Slack-backed chat client as a five-component system:

- `chat_client_api`: the abstract `ChatClient` contract and DTOs.
- `slack_client_impl`: the direct Slack implementation for local use.
- `chat_client_service`: the FastAPI deployment unit with Slack OAuth and session-token auth.
- `chat_client_service_api_client`: the OpenAPI-generated HTTP client for the service.
- `chat_client_adapter`: an adapter that implements `ChatClient` by calling the remote service.

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
uv run uvicorn chat_client_service.main:app --reload
```

Use the remote adapter through the original interface:

```python
import chat_client_adapter
from chat_client_api import get_client

client = get_client()
channels = client.list_channels()
```

If `CHAT_CLIENT_SERVICE_SESSION_ID` is not set, the adapter creates a service auth session, opens the browser to Slack login, waits for the callback to complete, and then continues through the same `ChatClient` contract.

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
- `JIRA_SERVICE_BASE_URL`: base URL of the Jira service adapter.
- `JIRA_SERVICE_ACCESS_TOKEN`: bearer token for the Jira adapter.
- `TICKET_SERVICE_BASE_URL`: legacy fallback for the previous tracker adapter.
- `TICKET_BOARD_ID`: legacy fallback board identifier.

## Issue Tracker Integration (HW3)

This service is being updated to speak the Jira contract first, while keeping
the previous tracker path as a fallback until the Jira team sends live details.

Implemented endpoints:

- `GET /issues?ticket_status=open`: list issues by status.
- `GET /issues/{issue_id}`: fetch one issue by ID.
- `POST /issues`: create an issue.
- `PATCH /issues/{issue_id}/status`: update issue status.
- Legacy aliases remain available on `/tickets` during transition.

The AI endpoint `POST /ai/chat` now also exposes issue tools:

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

- `ruff` passes with the handwritten codebase.
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

### Platform Configuration

- Platform: Render (Web Service)
- Branch: `Hw2`
- Root Directory: `components/chat_client_service`

Start command:

```bash
PYTHONPATH=src:../chat_client_api/src:../slack_client_impl/src:../chat_client_adapter/src:../chat_client_service_api_client/src uvicorn chat_client_service.main:app --host 0.0.0.0 --port $PORT
```

### Environment Variables

All secrets are stored in Render's Environment tab — none are committed to source control.

| Variable | Required | Description |
|---|---|---|
| `SLACK_CLIENT_ID` | yes | Slack App client ID (OAuth & Permissions page) |
| `SLACK_CLIENT_SECRET` | yes | Slack App client secret |
| `SLACK_REDIRECT_URI` | yes | Must exactly match the redirect URL in Slack App settings (`https://os-bmaq.onrender.com/auth/callback`) |
| `CHAT_CLIENT_SERVICE_BASE_URL` | yes | `https://os-bmaq.onrender.com` |
| `SLACK_SCOPES` | no | Defaults to `chat:write,channels:read,channels:history` |

### CI/CD Pipeline

CircleCI is configured in [.circleci/config.yml](.circleci/config.yml). Every push to `Hw2` triggers:

1. `uv sync --all-packages`
2. `ruff check .`
3. `mypy .`
4. `pytest --cov=components` — fails if coverage drops below 90%

To wire automatic deployment, add a `deploy` job that calls the Render deploy hook after a green build:

```yaml
deploy:
  docker:
    - image: cimg/base:stable
  steps:
    - run:
        name: Trigger Render deploy
        command: curl -X POST "$RENDER_DEPLOY_HOOK_URL"
```

Store `RENDER_DEPLOY_HOOK_URL` as a CircleCI environment variable and add `requires: [test]` to the workflow.
