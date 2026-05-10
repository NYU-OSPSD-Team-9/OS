# Chat Client Service

`chat_client_service` is the FastAPI deployment unit for HW2.

## Responsibilities

- Expose `/health`
- Start and complete Slack OAuth
- Store remote session state keyed by service session ID
- Serve `/channels`, `/messages`, and auth-session endpoints

## Local Run

```bash
export CHAT_CLIENT_SERVICE_BASE_URL="http://localhost:8000"
export SLACK_CLIENT_ID="your-slack-client-id"
export SLACK_CLIENT_SECRET="your-slack-client-secret"
export SLACK_REDIRECT_URI="http://localhost:8000/auth/callback"
uv run uvicorn chat_client_service.main:app --reload
```

## Important Endpoints

- `POST /auth/sessions`
- `GET /auth/login`
- `GET /auth/callback`
- `GET /auth/sessions/{session_id}`
- `DELETE /auth/sessions/{session_id}`
- `GET /channels`
- `POST /messages`
- `GET /messages`

The service expects `X-Session-ID` on the chat operation endpoints.
