# Chat Client Service

HW2 turns the chat client into a deployable service while preserving the original `ChatClient` interface.

## Components

- `chat_client_api`
- `slack_client_impl`
- `chat_client_service`
- `chat_client_service_api_client`
- `chat_client_adapter`

## Result

Consumer code can still call the same `ChatClient` methods whether the implementation is local (`slack_client_impl`) or remote (`chat_client_adapter`).
