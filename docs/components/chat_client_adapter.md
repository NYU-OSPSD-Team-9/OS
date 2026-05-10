# Chat Client Adapter

`chat_client_adapter` re-implements `ChatClient` on top of the generated service API client.

## What It Hides

- auth-session creation
- polling for OAuth completion
- HTTP request details
- DTO mapping from generated models back to the original interface objects

## Consumer View

The consumer still sees the same `ChatClient` methods:

- `list_channels()`
- `send_message(channel, text)`
- `get_messages(channel, limit, cursor)`

The only difference is that the injected implementation now talks to the remote service.
