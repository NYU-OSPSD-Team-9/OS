# Slack Client Implementation

This component is the direct Slack-backed `ChatClient` implementation used for local execution.

## Setup

```bash
export SLACK_BOT_TOKEN="xoxb-your-token"
```

## Usage

```python
import slack_client_impl
from chat_client_api import get_client

client = get_client()
channels = client.list_channels()
```

## Notes

- Importing the package registers the implementation automatically.
- The implementation uses the Slack Web API directly through `slack_sdk`.
- This path is useful for local development and dependency-injection sanity checks.

See [the component docs](../../docs/components/slack_client_impl.md) for more detail.
