"""Tests for the chat client FastAPI service."""

from __future__ import annotations

import os
from unittest import mock
from urllib.parse import parse_qs, urlparse

import httpx
from chat_client_api.client import Channel, Message
from chat_client_service.main import (
    _session_store,
    app,
    reset_service_state,
)
from chat_client_service.models import AuthSession
from fastapi.testclient import TestClient

HTTP_200_OK = 200
HTTP_201_CREATED = 201
HTTP_302_FOUND = 302
HTTP_400_BAD_REQUEST = 400
HTTP_401_UNAUTHORIZED = 401
HTTP_404_NOT_FOUND = 404
HTTP_500_INTERNAL_SERVER_ERROR = 500
HTTP_502_BAD_GATEWAY = 502
HTTP_503_SERVICE_UNAVAILABLE = 503

client = TestClient(app)


def setup_function() -> None:
    """Reset in-memory service state before each test."""
    reset_service_state()


def _create_authenticated_session() -> str:
    session = _session_store.create_session()
    test_bot_token = "xoxb-test-token"
    _session_store.authenticate_session(
        session_id=session.session_id,
        slack_bot_token=test_bot_token,
        team_name="OSPSD",
    )
    return session.session_id


# ---------------------------------------------------------------------------
# Health & Metrics
# ---------------------------------------------------------------------------


def test_health() -> None:
    """Health endpoint should return an ok payload."""
    response = client.get("/health")
    assert response.status_code == HTTP_200_OK
    assert response.json() == {"status": "ok"}


def test_metrics_initial_state() -> None:
    """Metrics endpoint should return zeroed counters on a fresh service."""
    response = client.get("/metrics")
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert "total_requests" in data
    assert "success_rate" in data
    assert "average_latency_ms" in data


def test_metrics_prometheus_format() -> None:
    """Prometheus endpoint should return text/plain with metric lines."""
    response = client.get("/metrics/prometheus")
    assert response.status_code == HTTP_200_OK
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    assert "chat_requests_total" in body
    assert "chat_requests_success" in body
    assert "chat_requests_failed" in body
    assert "chat_success_rate" in body
    assert "chat_failure_rate" in body
    assert "chat_avg_latency_ms" in body


def test_dashboard_returns_html() -> None:
    """Dashboard endpoint should return the branded HTML telemetry page."""
    response = client.get("/dashboard")
    assert response.status_code == HTTP_200_OK
    assert "text/html" in response.headers["content-type"]
    body = response.text
    # Branded header and the JS hook that fetches /metrics on the page.
    assert "Chat Service Telemetry" in body
    assert "OSPSD" in body
    assert "/metrics" in body
    # Sections that prove the redesigned panels rendered, not the old shell.
    assert "Status Class Distribution" in body
    assert "AI Provider Usage" in body


def test_metrics_records_per_route_breakdown() -> None:
    """The /metrics snapshot should expose per-route, per-method, per-status counts."""
    expected_health_calls = 2
    client.get("/health")
    client.get("/health")
    client.get("/this-route-does-not-exist")  # 404 → domain_error

    response = client.get("/metrics")
    data = response.json()

    assert data["domain_error_count"] >= 1
    assert data["successful_requests"] >= expected_health_calls

    by_route = {(entry["route"], entry["method"]): entry for entry in data["by_route"]}
    health_entry = by_route[("/health", "GET")]
    assert health_entry["ok_count"] >= expected_health_calls
    assert health_entry["count"] == health_entry["ok_count"] + health_entry[
        "domain_error_count"
    ] + health_entry["infra_error_count"]


def test_prometheus_exposes_labeled_series() -> None:
    """Prometheus output should include per-route counters with labels."""
    client.get("/health")
    client.get("/health")
    client.get("/dashboard")

    response = client.get("/metrics/prometheus")
    body = response.text

    assert "chat_requests_by_route_total" in body
    assert 'route="/health"' in body
    assert 'method="GET"' in body
    assert 'status_class="ok"' in body
    assert "chat_request_latency_ms_avg" in body
    assert "chat_requests_domain_errors_total" in body
    assert "chat_requests_infra_errors_total" in body


def test_metrics_records_ai_token_usage() -> None:
    """_record_ai_usage should accumulate token + cost into the snapshot."""
    from ai_client_api.client import TokenUsage
    from chat_client_service.main import _record_ai_usage

    _record_ai_usage(
        TokenUsage(
            model="gpt-4o-mini",
            prompt_tokens=120,
            completion_tokens=30,
            total_tokens=150,
            estimated_cost_usd=0.000234,
        ),
    )
    _record_ai_usage(
        TokenUsage(
            model="gpt-4o-mini",
            prompt_tokens=80,
            completion_tokens=20,
            total_tokens=100,
            estimated_cost_usd=0.000156,
        ),
    )

    response = client.get("/metrics")
    ai_usage = response.json()["ai_usage"]
    assert ai_usage["calls_total"] == 2
    assert ai_usage["prompt_tokens_total"] == 200
    assert ai_usage["completion_tokens_total"] == 50
    assert ai_usage["total_tokens_total"] == 250
    assert ai_usage["estimated_cost_usd_total"] > 0


def test_prometheus_exposes_ai_usage_metrics() -> None:
    """Prometheus output should include AI token + cost counters."""
    from ai_client_api.client import TokenUsage
    from chat_client_service.main import _record_ai_usage

    _record_ai_usage(
        TokenUsage(
            model="gpt-4o-mini",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            estimated_cost_usd=0.0001,
        ),
    )
    body = client.get("/metrics/prometheus").text
    assert "chat_ai_calls_total" in body
    assert "chat_ai_prompt_tokens_total" in body
    assert "chat_ai_completion_tokens_total" in body
    assert "chat_ai_total_tokens_total" in body
    assert "chat_ai_estimated_cost_usd_total" in body


def test_record_ai_usage_with_none_is_noop() -> None:
    """_record_ai_usage should silently ignore None (no provider data)."""
    from chat_client_service.main import _record_ai_usage

    response = client.get("/metrics")
    before = response.json()["ai_usage"]["calls_total"]

    _record_ai_usage(None)

    response = client.get("/metrics")
    after = response.json()["ai_usage"]["calls_total"]
    assert after == before


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_create_auth_session() -> None:
    """Creating an auth session should return a session token and URLs."""
    with mock.patch.dict(
        os.environ,
        {"CHAT_CLIENT_SERVICE_BASE_URL": "http://testserver"},
        clear=False,
    ):
        response = client.post("/auth/sessions")

    assert response.status_code == HTTP_201_CREATED
    data = response.json()
    assert data["authenticated"] is False
    assert data["session_id"]
    assert data["login_url"].endswith(f"/auth/login?session_id={data['session_id']}")
    assert data["status_url"].endswith(f"/auth/sessions/{data['session_id']}")


def test_auth_login_redirects_to_slack() -> None:
    """Auth login should redirect to Slack with state and redirect_uri."""
    with mock.patch.dict(
        os.environ,
        {
            "CHAT_CLIENT_SERVICE_BASE_URL": "http://testserver",
            "SLACK_CLIENT_ID": "test-client-id",
            "SLACK_REDIRECT_URI": "http://testserver/auth/callback",
        },
        clear=False,
    ):
        session_id = client.post("/auth/sessions").json()["session_id"]
        response = client.get(
            "/auth/login",
            params={"session_id": session_id},
            follow_redirects=False,
        )

    assert response.status_code == HTTP_302_FOUND
    location = response.headers["location"]
    parsed = urlparse(location)
    params = parse_qs(parsed.query)

    assert parsed.netloc == "slack.com"
    assert params["client_id"] == ["test-client-id"]
    assert params["redirect_uri"] == ["http://testserver/auth/callback"]
    assert params["state"]


def test_auth_callback_requires_code() -> None:
    """Auth callback should fail if Slack does not send a code."""
    response = client.get("/auth/callback")
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "No code provided."


def test_auth_callback_authenticates_session() -> None:
    """Auth callback should exchange the Slack code and mark the session ready."""
    with mock.patch.dict(
        os.environ,
        {
            "CHAT_CLIENT_SERVICE_BASE_URL": "http://testserver",
            "SLACK_CLIENT_ID": "test-client-id",
            "SLACK_CLIENT_SECRET": "test-client-secret",
            "SLACK_REDIRECT_URI": "http://testserver/auth/callback",
        },
        clear=False,
    ):
        session_id = client.post("/auth/sessions").json()["session_id"]
        login_response = client.get(
            "/auth/login",
            params={"session_id": session_id},
            follow_redirects=False,
        )
        state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

        token_response = mock.MagicMock()
        token_response.raise_for_status.return_value = None
        token_response.json.return_value = {
            "ok": True,
            "access_token": "xoxb-slack-oauth-token",
            "team": {"name": "OSPSD Team 9"},
        }

        with mock.patch(
            "chat_client_service.main.httpx.Client.post",
            return_value=token_response,
        ):
            callback_response = client.get(
                "/auth/callback",
                params={"code": "oauth-code", "state": state},
            )

    assert callback_response.status_code == HTTP_200_OK
    assert callback_response.json()["status"] == "ok"

    status_response = client.get(f"/auth/sessions/{session_id}")
    assert status_response.status_code == HTTP_200_OK
    assert status_response.json() == {
        "session_id": session_id,
        "authenticated": True,
        "team_name": "OSPSD Team 9",
    }


def test_delete_auth_session_clears_state() -> None:
    """Deleting an auth session should remove it from the store."""
    session_id = _create_authenticated_session()

    response = client.delete(f"/auth/sessions/{session_id}")
    assert response.status_code == HTTP_200_OK
    assert response.json() == {"status": "ok"}

    status_response = client.get(f"/auth/sessions/{session_id}")
    assert status_response.status_code == HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------


def test_list_channels_requires_authenticated_session() -> None:
    """List channels should reject requests without a session header."""
    response = client.get("/channels")
    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "X-Session-ID header is required."


def test_list_channels() -> None:
    """List channels should serialize channel DTOs from the concrete client."""
    session_id = _create_authenticated_session()
    mock_client = mock.MagicMock()
    mock_client.get_channels.return_value = [
        Channel(
            channel_id="C001",
            name="general",
            is_private=False,
        ),
    ]

    with mock.patch(
        "chat_client_service.main.build_chat_client",
        return_value=mock_client,
    ):
        response = client.get("/channels", headers={"X-Session-ID": session_id})

    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "channels": [
            {
                "channel_id": "C001",
                "name": "general",
                "is_private": False,
                "channel_type": None,
            },
        ],
    }


def test_get_channel_success() -> None:
    """get_channel endpoint should return a single channel."""
    session_id = _create_authenticated_session()
    mock_client = mock.MagicMock()
    mock_client.get_channel.return_value = Channel(
        channel_id="C001",
        name="general",
        is_private=False,
    )

    with mock.patch(
        "chat_client_service.main.build_chat_client",
        return_value=mock_client,
    ):
        response = client.get("/channels/C001", headers={"X-Session-ID": session_id})

    assert response.status_code == HTTP_200_OK
    assert response.json()["channel_id"] == "C001"


def test_get_channel_not_found() -> None:
    """get_channel should return 404 when the channel does not exist."""
    session_id = _create_authenticated_session()
    mock_client = mock.MagicMock()
    mock_client.get_channel.side_effect = ValueError("Channel not found: C999")

    with mock.patch(
        "chat_client_service.main.build_chat_client",
        return_value=mock_client,
    ):
        response = client.get("/channels/C999", headers={"X-Session-ID": session_id})

    assert response.status_code == HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


def test_send_message() -> None:
    """Send message should forward the JSON body to the chat client."""
    session_id = _create_authenticated_session()
    mock_client = mock.MagicMock()
    mock_client.send_message.return_value = Message(
        message_id="C001:12345.678",
        channel="C001",
        text="Hello from service",
        sender="",
        timestamp="12345.678",
    )

    with mock.patch(
        "chat_client_service.main.build_chat_client",
        return_value=mock_client,
    ):
        response = client.post(
            "/messages",
            headers={"X-Session-ID": session_id},
            json={"channel": "C001", "text": "Hello from service"},
        )

    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "message_id": "C001:12345.678",
        "channel": "C001",
        "text": "Hello from service",
        "sender": "",
        "timestamp": "12345.678",
    }


def test_get_messages() -> None:
    """Get messages should serialize message DTOs from the chat client."""
    session_id = _create_authenticated_session()
    mock_client = mock.MagicMock()
    mock_client.get_messages.return_value = [
        Message(
            message_id="C001:12345.678",
            channel="C001",
            text="Hello",
            sender="U001",
            timestamp="12345.678",
        ),
    ]

    with mock.patch(
        "chat_client_service.main.build_chat_client",
        return_value=mock_client,
    ):
        response = client.get(
            "/messages",
            headers={"X-Session-ID": session_id},
            params={"channel": "C001", "limit": 5},
        )

    assert response.status_code == HTTP_200_OK
    assert response.json() == {
        "messages": [
            {
                "message_id": "C001:12345.678",
                "channel": "C001",
                "text": "Hello",
                "sender": "U001",
                "timestamp": "12345.678",
            },
        ],
    }


def test_get_message_success() -> None:
    """get_message endpoint should return a single message."""
    session_id = _create_authenticated_session()
    mock_client = mock.MagicMock()
    mock_client.get_message.return_value = Message(
        message_id="C001:12345.678",
        channel="C001",
        text="Hello",
        sender="U001",
        timestamp="12345.678",
    )

    with mock.patch(
        "chat_client_service.main.build_chat_client",
        return_value=mock_client,
    ):
        response = client.get(
            "/messages/C001:12345.678",
            headers={"X-Session-ID": session_id},
        )

    assert response.status_code == HTTP_200_OK
    assert response.json()["text"] == "Hello"


def test_get_message_not_found() -> None:
    """get_message should return 404 when message does not exist."""
    session_id = _create_authenticated_session()
    mock_client = mock.MagicMock()
    mock_client.get_message.side_effect = ValueError("Message not found")

    with mock.patch(
        "chat_client_service.main.build_chat_client",
        return_value=mock_client,
    ):
        response = client.get(
            "/messages/C001:99999",
            headers={"X-Session-ID": session_id},
        )

    assert response.status_code == HTTP_404_NOT_FOUND


def test_delete_message_success() -> None:
    """delete_message endpoint should return ok status."""
    session_id = _create_authenticated_session()
    mock_client = mock.MagicMock()
    mock_client.delete_message.return_value = None

    with mock.patch(
        "chat_client_service.main.build_chat_client",
        return_value=mock_client,
    ):
        response = client.delete(
            "/messages/C001:12345.678",
            headers={"X-Session-ID": session_id},
        )

    assert response.status_code == HTTP_200_OK
    assert response.json() == {"status": "ok"}


def test_delete_message_not_found() -> None:
    """delete_message should return 404 when message does not exist."""
    session_id = _create_authenticated_session()
    mock_client = mock.MagicMock()
    mock_client.delete_message.side_effect = ValueError("Message not found")

    with mock.patch(
        "chat_client_service.main.build_chat_client",
        return_value=mock_client,
    ):
        response = client.delete(
            "/messages/C001:99999",
            headers={"X-Session-ID": session_id},
        )

    assert response.status_code == HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# AI chat
# ---------------------------------------------------------------------------


def test_ai_chat_no_implementation_returns_503() -> None:
    """ai/chat should return 503 when no AI client is registered."""
    session_id = _create_authenticated_session()
    mock_client = mock.MagicMock()

    with (
        mock.patch(
            "chat_client_service.main.build_chat_client",
            return_value=mock_client,
        ),
        mock.patch(
            "chat_client_service.main.get_ai_client",
            side_effect=RuntimeError("No AI client implementation registered."),
        ),
        mock.patch("chat_client_service.main.AiTool"),
    ):
        response = client.post(
            "/ai/chat",
            headers={"X-Session-ID": session_id},
            json={"prompt": "hello"},
        )

    assert response.status_code == HTTP_503_SERVICE_UNAVAILABLE


def test_ai_chat_returns_reply() -> None:
    """ai/chat should return the AI model's reply."""
    session_id = _create_authenticated_session()
    mock_chat_client = mock.MagicMock()
    mock_ai = mock.MagicMock()
    mock_ai.send_message_with_tools.return_value = "Here are your channels!"

    with (
        mock.patch(
            "chat_client_service.main.build_chat_client",
            return_value=mock_chat_client,
        ),
        mock.patch("chat_client_service.main.get_ai_client", return_value=mock_ai),
        mock.patch("chat_client_service.main.AiTool", return_value=mock.MagicMock()),
    ):
        response = client.post(
            "/ai/chat",
            headers={"X-Session-ID": session_id},
            json={"prompt": "list my channels", "channel": "C001"},
        )

    assert response.status_code == HTTP_200_OK
    assert response.json()["reply"] == "Here are your channels!"


# ---------------------------------------------------------------------------
# Error paths / branch coverage
# ---------------------------------------------------------------------------


def test_channels_with_unauthenticated_session() -> None:
    """Channels should reject a session that exists but has not completed OAuth."""
    session = _session_store.create_session()
    response = client.get("/channels", headers={"X-Session-ID": session.session_id})
    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert "not authenticated" in response.json()["detail"]


def test_auth_callback_error_from_slack() -> None:
    """Callback should return 401 when Slack sends an error parameter."""
    response = client.get("/auth/callback", params={"error": "access_denied"})
    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert "access_denied" in response.json()["detail"]


def test_auth_callback_missing_state() -> None:
    """Callback should return 400 when the state parameter is absent."""
    response = client.get("/auth/callback", params={"code": "some-code"})
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "No state provided."


def test_auth_callback_invalid_state() -> None:
    """Callback should return 400 when the OAuth state is unknown or expired."""
    response = client.get(
        "/auth/callback",
        params={"code": "abc", "state": "unknown-state"},
    )
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "Invalid or expired OAuth state" in response.json()["detail"]


def test_auth_login_missing_slack_client_id() -> None:
    """Auth login should return 500 when SLACK_CLIENT_ID is not configured."""
    session = _session_store.create_session()
    with mock.patch.dict(os.environ, {}, clear=True):
        response = client.get(
            "/auth/login",
            params={"session_id": session.session_id},
            follow_redirects=False,
        )
    assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR


def test_auth_callback_missing_credentials() -> None:
    """Callback should return 500 when Slack OAuth credentials are not configured."""
    session = _session_store.create_session()
    _session_store.bind_state(session.session_id, "state-no-creds")
    with mock.patch.dict(os.environ, {}, clear=True):
        response = client.get(
            "/auth/callback",
            params={"code": "abc", "state": "state-no-creds"},
        )
    assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR


def test_auth_callback_httpx_error() -> None:
    """Callback should return 502 when the Slack token-exchange request fails."""
    session = _session_store.create_session()
    _session_store.bind_state(session.session_id, "state-http-error")
    mock_resp = mock.MagicMock()
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "upstream error",
        request=mock.MagicMock(),
        response=mock.MagicMock(),
    )
    with mock.patch.dict(
        os.environ,
        {"SLACK_CLIENT_ID": "id", "SLACK_CLIENT_SECRET": "secret"},
        clear=False,
    ):
        with mock.patch(
            "chat_client_service.main.httpx.Client.post",
            return_value=mock_resp,
        ):
            response = client.get(
                "/auth/callback",
                params={"code": "abc", "state": "state-http-error"},
            )
    assert response.status_code == HTTP_502_BAD_GATEWAY


def test_auth_callback_non_dict_slack_response() -> None:
    """Callback should return 502 when Slack returns a non-dict token payload."""
    session = _session_store.create_session()
    _session_store.bind_state(session.session_id, "state-bad-payload")
    mock_resp = mock.MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = ["not", "a", "dict"]
    with mock.patch.dict(
        os.environ,
        {"SLACK_CLIENT_ID": "id", "SLACK_CLIENT_SECRET": "secret"},
        clear=False,
    ):
        with mock.patch(
            "chat_client_service.main.httpx.Client.post",
            return_value=mock_resp,
        ):
            response = client.get(
                "/auth/callback",
                params={"code": "abc", "state": "state-bad-payload"},
            )
    assert response.status_code == HTTP_502_BAD_GATEWAY


def test_auth_callback_slack_token_exchange_failed() -> None:
    """Callback should return 401 when Slack returns ok=False in the token response."""
    session = _session_store.create_session()
    _session_store.bind_state(session.session_id, "state-slack-err")
    mock_resp = mock.MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"ok": False, "error": "invalid_code"}
    with mock.patch.dict(
        os.environ,
        {"SLACK_CLIENT_ID": "id", "SLACK_CLIENT_SECRET": "secret"},
        clear=False,
    ):
        with mock.patch(
            "chat_client_service.main.httpx.Client.post",
            return_value=mock_resp,
        ):
            response = client.get(
                "/auth/callback",
                params={"code": "abc", "state": "state-slack-err"},
            )
    assert response.status_code == HTTP_401_UNAUTHORIZED


def test_auth_callback_missing_access_token() -> None:
    """Callback should return 500 when the Slack response omits access_token."""
    session = _session_store.create_session()
    _session_store.bind_state(session.session_id, "state-no-token")
    mock_resp = mock.MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"ok": True}
    with mock.patch.dict(
        os.environ,
        {"SLACK_CLIENT_ID": "id", "SLACK_CLIENT_SECRET": "secret"},
        clear=False,
    ):
        with mock.patch(
            "chat_client_service.main.httpx.Client.post",
            return_value=mock_resp,
        ):
            response = client.get(
                "/auth/callback",
                params={"code": "abc", "state": "state-no-token"},
            )
    assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR


def test_auth_callback_team_name_not_a_dict() -> None:
    """Callback should record None team_name when team payload is not a dict."""
    session = _session_store.create_session()
    _session_store.bind_state(session.session_id, "state-team-str")
    mock_resp = mock.MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "ok": True,
        "access_token": "xoxb-token",
        "team": "just-a-string",
    }
    with mock.patch.dict(
        os.environ,
        {"SLACK_CLIENT_ID": "id", "SLACK_CLIENT_SECRET": "secret"},
        clear=False,
    ):
        with mock.patch(
            "chat_client_service.main.httpx.Client.post",
            return_value=mock_resp,
        ):
            response = client.get(
                "/auth/callback",
                params={"code": "abc", "state": "state-team-str"},
            )
    assert response.status_code == HTTP_200_OK
    status = client.get(f"/auth/sessions/{session.session_id}")
    assert status.json()["team_name"] is None


def test_auth_callback_team_name_empty_string() -> None:
    """Callback should succeed and record None team_name when team name is empty."""
    session = _session_store.create_session()
    _session_store.bind_state(session.session_id, "state-empty-name")
    mock_resp = mock.MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "ok": True,
        "access_token": "xoxb-token",
        "team": {"name": ""},
    }
    with mock.patch.dict(
        os.environ,
        {"SLACK_CLIENT_ID": "id", "SLACK_CLIENT_SECRET": "secret"},
        clear=False,
    ):
        with mock.patch(
            "chat_client_service.main.httpx.Client.post",
            return_value=mock_resp,
        ):
            response = client.get(
                "/auth/callback",
                params={"code": "abc", "state": "state-empty-name"},
            )
    assert response.status_code == HTTP_200_OK
    status = client.get(f"/auth/sessions/{session.session_id}")
    assert status.json()["team_name"] is None


def test_delete_session_also_removes_bound_oauth_state() -> None:
    """Deleting a session with a pending OAuth state should clean up the state index."""
    with mock.patch.dict(os.environ, {"SLACK_CLIENT_ID": "test-id"}, clear=False):
        session_id = client.post("/auth/sessions").json()["session_id"]
        client.get(
            "/auth/login",
            params={"session_id": session_id},
            follow_redirects=False,
        )

    client.delete(f"/auth/sessions/{session_id}")

    assert _session_store.get_session(session_id) is None
    assert not any(
        v == session_id
        for v in _session_store._oauth_state_to_session_id.values()
    )


def test_build_chat_client_returns_slack_client() -> None:
    """build_chat_client should return a ChatClient implementation."""
    from chat_client_api.client import ChatClient
    from chat_client_service.main import build_chat_client

    result = build_chat_client("xoxb-test-token")
    assert isinstance(result, ChatClient)


def test_create_app_returns_fastapi_instance() -> None:
    """create_app should return the configured FastAPI application."""
    from chat_client_service.main import create_app
    from fastapi import FastAPI

    result = create_app()
    assert isinstance(result, FastAPI)


def test_get_authenticated_client_token_none_guard() -> None:
    """Authenticated client helper returns 401 when token is unexpectedly None."""
    session_id = _create_authenticated_session()
    with mock.patch.object(
        _session_store,
        "require_authenticated_session",
        return_value=AuthSession(session_id=session_id, slack_bot_token=None),
    ):
        response = client.get("/channels", headers={"X-Session-ID": session_id})
    assert response.status_code == HTTP_401_UNAUTHORIZED
