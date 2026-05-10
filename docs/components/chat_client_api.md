# Chat Client API

`chat_client_api` is the stable contract shared by the local and remote implementations.

## Interface

- `send_message(channel, text)`
- `list_channels()`
- `get_messages(channel, limit=10, cursor=None)`

## DTOs

- `Channel`
- `Message`
- `SendMessageResponse`

## Dependency Injection

The module exposes `register_client()` and `get_client()` so implementations can register themselves on import.

That means the same consumer code works with either:

- `import slack_client_impl`
- `import chat_client_adapter`
