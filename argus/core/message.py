"""Argus message model."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ArgusMessage:
    """A routed Argus message between human and agent nodes."""

    from_id: str
    to: list[str]
    text: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reply_to: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)
    is_group: bool = field(init=False)

    def __post_init__(self) -> None:
        self.is_group = len(self.to) != 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize the message to a dictionary."""
        return {
            "id": self.id,
            "from_id": self.from_id,
            "to": self.to,
            "text": self.text,
            "reply_to": self.reply_to,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "is_group": self.is_group,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArgusMessage:
        """Deserialize a message from a dictionary."""
        return cls(
            id=data["id"],
            from_id=data["from_id"],
            to=list(data["to"]),
            text=data["text"],
            reply_to=data.get("reply_to"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=dict(data.get("metadata", {})),
        )


def make_private_message(from_id: str, to_id: str, text: str, **kwargs: Any) -> ArgusMessage:
    """Create a one-to-one private message."""
    return ArgusMessage(from_id=from_id, to=[to_id], text=text, **kwargs)


def make_group_message(
    from_id: str,
    text: str,
    to: list[str] | None = None,
    **kwargs: Any,
) -> ArgusMessage:
    """Create a group (one-to-many) message.

    An empty ``to`` list indicates a broadcast to all group members.
    """
    return ArgusMessage(from_id=from_id, to=to or [], text=text, **kwargs)
