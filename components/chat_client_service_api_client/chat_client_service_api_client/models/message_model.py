from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="MessageModel")


@_attrs_define
class MessageModel:
    """Serialized chat message response model.

    Attributes:
        message_id (str):
        channel (str):
        text (str):
        sender (str):
        timestamp (str):
    """

    message_id: str
    channel: str
    text: str
    sender: str
    timestamp: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        message_id = self.message_id

        channel = self.channel

        text = self.text

        sender = self.sender

        timestamp = self.timestamp

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "message_id": message_id,
                "channel": channel,
                "text": text,
                "sender": sender,
                "timestamp": timestamp,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        message_id = d.pop("message_id")

        channel = d.pop("channel")

        text = d.pop("text")

        sender = d.pop("sender")

        timestamp = d.pop("timestamp")

        message_model = cls(
            message_id=message_id,
            channel=channel,
            text=text,
            sender=sender,
            timestamp=timestamp,
        )

        message_model.additional_properties = d
        return message_model

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
