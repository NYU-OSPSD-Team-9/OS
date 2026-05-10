from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.get_messages_response import GetMessagesResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    channel: str,
    limit: int | Unset = 10,
    cursor: None | str | Unset = UNSET,
    x_session_id: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_session_id, Unset):
        headers["X-Session-ID"] = x_session_id

    params: dict[str, Any] = {}

    params["channel"] = channel

    params["limit"] = limit

    json_cursor: None | str | Unset
    if isinstance(cursor, Unset):
        json_cursor = UNSET
    else:
        json_cursor = cursor
    params["cursor"] = json_cursor

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/messages",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> GetMessagesResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = GetMessagesResponse.from_dict(response.json())

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
) -> Response[GetMessagesResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    channel: str,
    limit: int | Unset = 10,
    cursor: None | str | Unset = UNSET,
    x_session_id: None | str | Unset = UNSET,
) -> Response[GetMessagesResponse | HTTPValidationError]:
    """Get Messages

     Get recent messages from a Slack channel.

    Args:
        channel (str):
        limit (int | Unset):  Default: 10.
        cursor (None | str | Unset):
        x_session_id (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetMessagesResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        channel=channel,
        limit=limit,
        cursor=cursor,
        x_session_id=x_session_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    channel: str,
    limit: int | Unset = 10,
    cursor: None | str | Unset = UNSET,
    x_session_id: None | str | Unset = UNSET,
) -> GetMessagesResponse | HTTPValidationError | None:
    """Get Messages

     Get recent messages from a Slack channel.

    Args:
        channel (str):
        limit (int | Unset):  Default: 10.
        cursor (None | str | Unset):
        x_session_id (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetMessagesResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        channel=channel,
        limit=limit,
        cursor=cursor,
        x_session_id=x_session_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    channel: str,
    limit: int | Unset = 10,
    cursor: None | str | Unset = UNSET,
    x_session_id: None | str | Unset = UNSET,
) -> Response[GetMessagesResponse | HTTPValidationError]:
    """Get Messages

     Get recent messages from a Slack channel.

    Args:
        channel (str):
        limit (int | Unset):  Default: 10.
        cursor (None | str | Unset):
        x_session_id (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetMessagesResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        channel=channel,
        limit=limit,
        cursor=cursor,
        x_session_id=x_session_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    channel: str,
    limit: int | Unset = 10,
    cursor: None | str | Unset = UNSET,
    x_session_id: None | str | Unset = UNSET,
) -> GetMessagesResponse | HTTPValidationError | None:
    """Get Messages

     Get recent messages from a Slack channel.

    Args:
        channel (str):
        limit (int | Unset):  Default: 10.
        cursor (None | str | Unset):
        x_session_id (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetMessagesResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            channel=channel,
            limit=limit,
            cursor=cursor,
            x_session_id=x_session_id,
        )
    ).parsed
