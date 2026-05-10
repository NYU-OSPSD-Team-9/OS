# Architecture

## Runtime Paths

### Local path

`chat_client_api` -> `slack_client_impl` -> Slack Web API

### Remote path

`chat_client_api` -> `chat_client_adapter` -> `chat_client_service_api_client` -> `chat_client_service` -> `slack_client_impl` -> Slack Web API

## OAuth Flow

1. The adapter asks the service to create an auth session.
2. The service returns a login URL and session ID.
3. The adapter opens the browser to the service login URL.
4. The service redirects to Slack.
5. Slack redirects back to `/auth/callback`.
6. The service exchanges the code for a Slack token and stores it under the service session ID.
7. The adapter polls `/auth/sessions/{session_id}` until the session becomes authenticated.

## Service Boundary

- `/health` supports operational checks.
- `/auth/*` endpoints manage OAuth and remote session state.
- `/channels` and `/messages` expose the original chat contract over HTTP.
