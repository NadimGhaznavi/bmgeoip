"""Versioned message envelope compatible with the AX3L transport."""

from dataclasses import dataclass, field
import json
from typing import Any

from bmgeoip.constants.DZMQ import DZMQ


@dataclass
class ZMQMsg:
    sender: str
    method: str
    target: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("sender", "method"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a nonempty string")
        if self.target is not None and not isinstance(self.target, str):
            raise TypeError("target must be a string or None")
        if not isinstance(self.payload, dict):
            raise TypeError("payload must be an object")

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": DZMQ.PROTOCOL_VERSION,
            "sender": self.sender, "target": self.target,
            "method": self.method, "payload": self.payload,
        }

    def to_json(self) -> bytes:
        return json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False).encode("utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZMQMsg":
        if not isinstance(data, dict):
            raise TypeError("message must be an object")
        version = data["protocol_version"]
        if type(version) is not int or version != DZMQ.PROTOCOL_VERSION:
            raise ValueError(f"Unsupported ZMQ protocol version: {version}")
        return cls(sender=data["sender"], target=data["target"],
                   method=data["method"], payload=data["payload"])

    @classmethod
    def from_json(cls, data: bytes) -> "ZMQMsg":
        return cls.from_dict(json.loads(data.decode("utf-8")))
