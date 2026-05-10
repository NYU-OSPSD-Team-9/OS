# Slack Client Implementation

`slack_client_impl` is the direct Slack implementation used when the application runs locally without the service boundary.

## Behavior

- Builds a `slack_sdk.WebClient` from `SLACK_BOT_TOKEN`
- Sends messages with `chat.postMessage`
- Lists channels with `conversations.list`
- Reads message history with `conversations.history`

## Registration

Importing the package registers the Slack client factory with `chat_client_api`.

## Configuration

- `SLACK_BOT_TOKEN`

## Relationship to HW2

The FastAPI service still delegates its business logic to this component once OAuth has produced a Slack token for the current remote session.
