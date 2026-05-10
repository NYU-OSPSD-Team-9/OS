from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="SendMessageResponseModel")


@_attrs_define
class SendMessageResponseModel:
    """Send message response model.

    Attributes:
        message_id (str):
        channel (str):
        timestamp (str):
        ok (bool):
    """

    message_id: str
    channel: str
    timestamp: str
    ok: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        message_id = self.message_id

        channel = self.channel

        timestamp = self.timestamp

        ok = self.ok

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "message_id": message_id,
                "channel": channel,
                "timestamp": timestamp,
                "ok": ok,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        message_id = d.pop("message_id")

        channel = d.pop("channel")

        timestamp = d.pop("timestamp")

        ok = d.pop("ok")

        send_message_response_model = cls(
            message_id=message_id,
            channel=channel,
            timestamp=timestamp,
            ok=ok,
        )

        send_message_response_model.additional_properties = d
        return send_message_response_model

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
