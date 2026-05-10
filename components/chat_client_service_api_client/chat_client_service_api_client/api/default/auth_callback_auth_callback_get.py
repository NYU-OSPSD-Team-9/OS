from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.auth_callback_response import AuthCallbackResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    code: str | Unset = "",
    state: str | Unset = "",
    error: str | Unset = "",
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["code"] = code

    params["state"] = state

    params["error"] = error

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/auth/callback",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AuthCallbackResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AuthCallbackResponse.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[AuthCallbackResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    code: str | Unset = "",
    state: str | Unset = "",
    error: str | Unset = "",
) -> Response[AuthCallbackResponse | HTTPValidationError]:
    """Auth Callback

     Complete the Slack OAuth authorization-code flow.

    Args:
        code (str | Unset):  Default: ''.
        state (str | Unset):  Default: ''.
        error (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AuthCallbackResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        code=code,
        state=state,
        error=error,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    code: str | Unset = "",
    state: str | Unset = "",
    error: str | Unset = "",
) -> AuthCallbackResponse | HTTPValidationError | None:
    """Auth Callback

     Complete the Slack OAuth authorization-code flow.

    Args:
        code (str | Unset):  Default: ''.
        state (str | Unset):  Default: ''.
        error (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AuthCallbackResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        code=code,
        state=state,
        error=error,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    code: str | Unset = "",
    state: str | Unset = "",
    error: str | Unset = "",
) -> Response[AuthCallbackResponse | HTTPValidationError]:
    """Auth Callback

     Complete the Slack OAuth authorization-code flow.

    Args:
        code (str | Unset):  Default: ''.
        state (str | Unset):  Default: ''.
        error (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AuthCallbackResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        code=code,
        state=state,
        error=error,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    code: str | Unset = "",
    state: str | Unset = "",
    error: str | Unset = "",
) -> AuthCallbackResponse | HTTPValidationError | None:
    """Auth Callback

     Complete the Slack OAuth authorization-code flow.

    Args:
        code (str | Unset):  Default: ''.
        state (str | Unset):  Default: ''.
        error (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AuthCallbackResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            code=code,
            state=state,
            error=error,
        )
    ).parsed
