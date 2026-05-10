from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="AuthSessionResponse")


@_attrs_define
class AuthSessionResponse:
    """Created auth session response model.

    Attributes:
        session_id (str):
        authenticated (bool):
        login_url (str):
        status_url (str):
    """

    session_id: str
    authenticated: bool
    login_url: str
    status_url: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        session_id = self.session_id

        authenticated = self.authenticated

        login_url = self.login_url

        status_url = self.status_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "session_id": session_id,
                "authenticated": authenticated,
                "login_url": login_url,
                "status_url": status_url,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        session_id = d.pop("session_id")

        authenticated = d.pop("authenticated")

        login_url = d.pop("login_url")

        status_url = d.pop("status_url")

        auth_session_response = cls(
            session_id=session_id,
            authenticated=authenticated,
            login_url=login_url,
            status_url=status_url,
        )

        auth_session_response.additional_properties = d
        return auth_session_response

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
