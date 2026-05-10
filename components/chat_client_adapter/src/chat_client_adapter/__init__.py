"""Chat client service adapter package."""

import chat_client_adapter.client  # noqa: F401
from chat_client_adapter.client import (
    ChatClientServiceAdapter as ChatClientServiceAdapter,
)
from chat_client_adapter.client import ServiceAuthSession as ServiceAuthSession

__version__ = "0.1.0"
