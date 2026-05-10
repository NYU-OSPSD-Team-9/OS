# Chat Client Service API Client

This package is generated from the FastAPI OpenAPI schema and provides typed HTTP bindings for the service endpoints.

## Regeneration

```bash
uv run python -c "from chat_client_service.main import app; import json, pathlib; pathlib.Path('openapi-chat-client-service.json').write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')"
uv run openapi-python-client generate --path openapi-chat-client-service.json --config openapi-python-client-config.yml --meta uv --output-path components/chat_client_service_api_client --overwrite
```

## Usage

```python
from chat_client_service_api_client.client import Client
from chat_client_service_api_client.api.default import create_auth_session_auth_sessions_post

client = Client(base_url="http://localhost:8000", raise_on_unexpected_status=True)
session = create_auth_session_auth_sessions_post.sync(client=client)
```

## Notes

- The generated package is consumed by `chat_client_adapter`.
- The generated modules are not intended for manual edits.
- Root lint/type/coverage rules target handwritten code, not the generated package internals.
