# Chat Client Service

`chat_client_service` is the FastAPI deployment unit.

## Endpoints

- `GET /health`
- `POST /auth/sessions`
- `GET /auth/login`
- `GET /auth/callback`
- `GET /auth/sessions/{session_id}`
- `DELETE /auth/sessions/{session_id}`
- `GET /channels`
- `POST /messages`
- `GET /messages`

## Auth Model

The service creates an auth session first, then stores the Slack token under that service session ID after Slack redirects back to `/auth/callback`.

## Headers

Chat operations require `X-Session-ID`.
