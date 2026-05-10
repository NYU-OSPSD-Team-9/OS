# Chat Client Adapter

`chat_client_adapter` implements `ChatClient` by calling the remote FastAPI service through the generated OpenAPI client.

## Usage

```python
import chat_client_adapter
from chat_client_api import get_client

client = get_client()
messages = client.get_messages("C001", limit=10)
```

## Auth Flow

- The adapter uses `CHAT_CLIENT_SERVICE_BASE_URL` to reach the service.
- If `CHAT_CLIENT_SERVICE_SESSION_ID` is missing, the adapter creates a new auth session on the service.
- On the first remote operation, it opens the browser to the service login URL, waits for the Slack callback to complete, stores the session ID in-process, and then retries the operation through the same `ChatClient` contract.

## Environment Variables

- `CHAT_CLIENT_SERVICE_BASE_URL`
- `CHAT_CLIENT_SERVICE_SESSION_ID`
- `CHAT_CLIENT_SERVICE_OPEN_BROWSER`
- `CHAT_CLIENT_SERVICE_AUTH_TIMEOUT_SECONDS`
- `CHAT_CLIENT_SERVICE_POLL_INTERVAL_SECONDS`
