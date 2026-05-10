from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.send_message_request import SendMessageRequest
from ...models.send_message_response_model import SendMessageResponseModel
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: SendMessageRequest,
    x_session_id: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_session_id, Unset):
        headers["X-Session-ID"] = x_session_id

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/messages",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | SendMessageResponseModel | None:
    if response.status_code == 200:
        response_200 = SendMessageResponseModel.from_dict(response.json())

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
) -> Response[HTTPValidationError | SendMessageResponseModel]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: SendMessageRequest,
    x_session_id: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | SendMessageResponseModel]:
    """Send Message

     Send a message to a Slack channel.

    Args:
        x_session_id (None | str | Unset):
        body (SendMessageRequest): Send message request model.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SendMessageResponseModel]
    """

    kwargs = _get_kwargs(
        body=body,
        x_session_id=x_session_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: SendMessageRequest,
    x_session_id: None | str | Unset = UNSET,
) -> HTTPValidationError | SendMessageResponseModel | None:
    """Send Message

     Send a message to a Slack channel.

    Args:
        x_session_id (None | str | Unset):
        body (SendMessageRequest): Send message request model.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SendMessageResponseModel
    """

    return sync_detailed(
        client=client,
        body=body,
        x_session_id=x_session_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: SendMessageRequest,
    x_session_id: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | SendMessageResponseModel]:
    """Send Message

     Send a message to a Slack channel.

    Args:
        x_session_id (None | str | Unset):
        body (SendMessageRequest): Send message request model.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SendMessageResponseModel]
    """

    kwargs = _get_kwargs(
        body=body,
        x_session_id=x_session_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: SendMessageRequest,
    x_session_id: None | str | Unset = UNSET,
) -> HTTPValidationError | SendMessageResponseModel | None:
    """Send Message

     Send a message to a Slack channel.

    Args:
        x_session_id (None | str | Unset):
        body (SendMessageRequest): Send message request model.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SendMessageResponseModel
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_session_id=x_session_id,
        )
    ).parsed
