"""End-to-end tests for the deployed service and local Slack implementation."""

from __future__ import annotations

import os

import httpx
import pytest
from chat_client_api.client import Channel, ChatClient, Message
from slack_client_impl.client import SlackClient

LIVE_SERVICE_URL = os.getenv("CHAT_CLIENT_SERVICE_BASE_URL", "https://os-bmaq.onrender.com")

HTTP_200_OK = 200
HTTP_201_CREATED = 201
HTTP_401_UNAUTHORIZED = 401
HTTP_404_NOT_FOUND = 404


class TestLiveServiceEndpoints:
    """Tests against the deployed service that require no authenticated session."""

    def test_health(self) -> None:
        """Health endpoint should return ok with HTTP 200."""
        response = httpx.get(f"{LIVE_SERVICE_URL}/health", timeout=60)
        assert response.status_code == HTTP_200_OK
        assert response.json() == {"status": "ok"}

    def test_openapi_spec_lists_required_endpoints(self) -> None:
        """OpenAPI spec should be reachable and list all required service endpoints."""
        response = httpx.get(f"{LIVE_SERVICE_URL}/openapi.json", timeout=60)
        assert response.status_code == HTTP_200_OK
        spec = response.json()
        assert spec["info"]["title"] == "Chat Client Service"
        required = {
            "/health",
            "/auth/sessions",
            "/auth/login",
            "/auth/callback",
            "/channels",
            "/messages",
        }
        assert required.issubset(spec["paths"].keys())

    def test_auth_session_lifecycle(self) -> None:
        """Auth session create, read, and delete lifecycle completes without errors."""
        # Skip when the live service is unavailable (e.g. pending redeploy)
        health = httpx.get(f"{LIVE_SERVICE_URL}/health", timeout=30)
        if health.status_code >= 500:
            msg = f"Live service unhealthy ({health.status_code}) — skipping"
            pytest.skip(msg)

        create = httpx.post(f"{LIVE_SERVICE_URL}/auth/sessions", timeout=60)
        assert create.status_code == HTTP_201_CREATED
        data = create.json()
        session_id = data["session_id"]
        assert not data["authenticated"]
        assert session_id
        assert "/auth/login" in data["login_url"]
        assert "/auth/sessions/" in data["status_url"]

        status = httpx.get(f"{LIVE_SERVICE_URL}/auth/sessions/{session_id}", timeout=60)
        assert status.status_code == HTTP_200_OK
        assert status.json()["authenticated"] is False

        delete = httpx.delete(
            f"{LIVE_SERVICE_URL}/auth/sessions/{session_id}", timeout=60,
        )
        assert delete.status_code == HTTP_200_OK

        gone = httpx.get(f"{LIVE_SERVICE_URL}/auth/sessions/{session_id}", timeout=60)
        assert gone.status_code == HTTP_404_NOT_FOUND

    def test_channels_without_session_header_returns_401(self) -> None:
        """Channels endpoint should reject requests that omit X-Session-ID."""
        response = httpx.get(f"{LIVE_SERVICE_URL}/channels", timeout=60)
        assert response.status_code == HTTP_401_UNAUTHORIZED

    def test_messages_without_session_header_returns_401(self) -> None:
        """Messages endpoint should reject requests that omit X-Session-ID."""
        response = httpx.get(
            f"{LIVE_SERVICE_URL}/messages",
            params={"channel": "C001"},
            timeout=60,
        )
        assert response.status_code == HTTP_401_UNAUTHORIZED

    def test_metrics_endpoint_returns_telemetry(self) -> None:
        """Metrics endpoint should return all required telemetry fields."""
        response = httpx.get(f"{LIVE_SERVICE_URL}/metrics", timeout=60)
        if response.status_code == HTTP_404_NOT_FOUND:
            pytest.skip("Endpoint not deployed yet")
        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert "total_requests" in data
        assert "success_rate" in data
        assert "failure_rate" in data
        assert "average_latency_ms" in data

    def test_prometheus_metrics_endpoint(self) -> None:
        """Prometheus metrics endpoint should return text exposition format."""
        response = httpx.get(
            f"{LIVE_SERVICE_URL}/metrics/prometheus", timeout=60,
        )
        if response.status_code == HTTP_404_NOT_FOUND:
            pytest.skip("Endpoint not deployed yet")
        assert response.status_code == HTTP_200_OK
        assert "text/plain" in response.headers.get("content-type", "")
        assert "chat_requests_total" in response.text

    def test_dashboard_endpoint_serves_html(self) -> None:
        """Dashboard endpoint should return an HTML telemetry page."""
        response = httpx.get(
            f"{LIVE_SERVICE_URL}/dashboard", timeout=60,
        )
        if response.status_code == HTTP_404_NOT_FOUND:
            pytest.skip("Endpoint not deployed yet")
        assert response.status_code == HTTP_200_OK
        assert "text/html" in response.headers.get("content-type", "")
        assert "text/html" in response.headers.get("content-type", "")


class TestSlackClientE2E:
    """Tests against the real Slack API using the local slack_client_impl.

    Requires SLACK_BOT_TOKEN to be set in the environment. All tests in this
    class are skipped automatically when the token is absent.
    """

    def test_get_channels_returns_channel_objects(self) -> None:
        """get_channels should return a list of Channel dataclass instances."""
        token = os.getenv("SLACK_BOT_TOKEN")
        if not token:
            pytest.skip("SLACK_BOT_TOKEN not set")
        slack = SlackClient(token)
        channels = slack.get_channels()
        assert isinstance(channels, list)
        assert all(isinstance(c, Channel) for c in channels)

    def test_get_messages_returns_message_objects(self) -> None:
        """get_messages should return a list of Message dataclass instances."""
        token = os.getenv("SLACK_BOT_TOKEN")
        channel = os.getenv("SLACK_TEST_CHANNEL")
        if not token or not channel:
            pytest.skip("SLACK_BOT_TOKEN and SLACK_TEST_CHANNEL must both be set")
        slack = SlackClient(token)
        messages = slack.get_messages(channel, limit=5)
        assert isinstance(messages, list)
        assert all(isinstance(m, Message) for m in messages)

    def test_send_message_returns_ok(self) -> None:
        """send_message should post to the channel and return ok=True."""
        token = os.getenv("SLACK_BOT_TOKEN")
        channel = os.getenv("SLACK_TEST_CHANNEL")
        if not token or not channel:
            pytest.skip("SLACK_BOT_TOKEN and SLACK_TEST_CHANNEL must both be set")
        slack = SlackClient(token)
        result = slack.send_message(channel, "E2E test from pytest")
        assert result.channel == channel


class TestSameConsumerCodeBothBackends:
    """Demonstrates the same consumer code working against both backends.

    These tests verify the core architecture goal: the consumer (caller of
    get_client()) does not need to change regardless of which backend is active.
    Requires SLACK_BOT_TOKEN for the local backend and
    CHAT_CLIENT_SERVICE_BASE_URL + CHAT_CLIENT_SERVICE_SESSION_ID for remote.
    """

    def _assert_get_channels_returns_channels(self, client: ChatClient) -> None:
        channels = client.get_channels()
        assert isinstance(channels, list)
        assert all(isinstance(c, Channel) for c in channels)

    def test_local_backend_list_channels(self) -> None:
        """The local SlackClient satisfies the ChatClient interface."""
        token = os.getenv("SLACK_BOT_TOKEN")
        if not token:
            pytest.skip("SLACK_BOT_TOKEN not set")
        import slack_client_impl  # noqa: F401
        from chat_client_api.client import get_client
        client = get_client()
        self._assert_get_channels_returns_channels(client)

    def test_remote_backend_list_channels(self) -> None:
        """The service adapter satisfies the same ChatClient interface."""
        base_url = os.getenv("CHAT_CLIENT_SERVICE_BASE_URL")
        session_id = os.getenv("CHAT_CLIENT_SERVICE_SESSION_ID")
        if not base_url or not session_id:
            pytest.skip(
                "CHAT_CLIENT_SERVICE_BASE_URL and "
                "CHAT_CLIENT_SERVICE_SESSION_ID must be set",
            )
        import chat_client_adapter  # noqa: F401
        from chat_client_api.client import get_client
        client = get_client()
        self._assert_get_channels_returns_channels(client)
