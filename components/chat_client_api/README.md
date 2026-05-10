# Chat Client API

This package defines the stable interface shared by the local Slack implementation and the remote service adapter.

## Contract

- `send_message(channel, text) -> SendMessageResponse`
- `list_channels() -> list[Channel]`
- `get_messages(channel, limit=10, cursor=None) -> list[Message]`

## Dependency Injection

Importing an implementation package registers a factory:

```python
from chat_client_api import get_client

import slack_client_impl

client = get_client()
```

The same pattern works with the remote adapter:

```python
import chat_client_adapter
from chat_client_api import get_client

client = get_client()
```

## DTOs

- `Channel`
- `Message`
- `SendMessageResponse`

See [the component docs](../../docs/components/chat_client_api.md) for details.
