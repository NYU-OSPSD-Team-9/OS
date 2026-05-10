"""Slack chat client implementation."""

# Importing this module triggers registration in client.py
import slack_client_impl.client  # noqa: F401
from slack_client_impl.client import SlackClient as SlackClient

__version__ = "0.1.0"
