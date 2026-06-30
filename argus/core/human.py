"""Human-node presence and inbox management.

In production, human nodes represent real people. They come and go (online/offline),
need their messages preserved while away, and must not block agent work.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from argus.core.message import ArgusMessage
from argus.core.tree import CollaborationTree

HumanHandler = Callable[[ArgusMessage], Awaitable[None]]


@dataclass
class HumanPresence:
    """Runtime state for a single human node."""

    online: bool = False
    last_seen: datetime | None = None
    handler: HumanHandler | None = None
    inbox: deque[ArgusMessage] = field(default_factory=lambda: deque(maxlen=1000))


class HumanNodeManager:
    """Manage presence, message delivery and inboxing for human nodes.

    The manager is intentionally non-blocking for callers: ``deliver`` returns
    immediately after either handing the message to an online handler or storing
    it in the node's inbox. Agent work continues regardless of whether a human
    is currently online.
    """

    def __init__(
        self,
        tree: CollaborationTree,
        max_inbox_size: int = 1000,
        storage_dir: Path | str | None = None,
    ) -> None:
        self.tree = tree
        self._max_inbox_size = max_inbox_size
        self._storage_dir: Path | None = (
            Path(storage_dir).expanduser() if storage_dir else None
        )
        self._nodes: dict[str, HumanPresence] = {}
        self._lock = asyncio.Lock()

        for node in tree.nodes:
            if node.type == "human":
                self._nodes[node.id] = HumanPresence()

        self._load_all_inboxes()

    def node_ids(self) -> list[str]:
        """Return all known human node IDs."""
        return list(self._nodes.keys())

    async def register_handler(
        self,
        node_id: str,
        handler: HumanHandler,
    ) -> list[ArgusMessage]:
        """Mark a human node as online and drain any queued inbox messages.

        Returns the list of messages that were waiting in the inbox, so the
        caller can correlate what got flushed on login.
        """
        async with self._lock:
            presence = self._nodes.setdefault(node_id, HumanPresence())
            presence.handler = handler
            presence.online = True
            presence.last_seen = datetime.now(timezone.utc)
            pending = list(presence.inbox)
            presence.inbox.clear()

        self._save_inbox(node_id)

        for message in pending:
            try:
                await handler(message)
            except Exception:
                await self._return_to_inbox(node_id, message)

        return pending

    async def unregister_handler(self, node_id: str) -> None:
        """Mark a human node as offline; future messages go to the inbox."""
        async with self._lock:
            presence = self._nodes.get(node_id)
            if presence is not None:
                presence.handler = None
                presence.online = False

    async def heartbeat(self, node_id: str) -> None:
        """Update last-seen timestamp; keeps the node marked online."""
        async with self._lock:
            presence = self._nodes.get(node_id)
            if presence is not None:
                presence.last_seen = datetime.now(timezone.utc)
                if presence.handler is not None:
                    presence.online = True

    async def deliver(self, node_id: str, message: ArgusMessage) -> bool:
        """Deliver a message to a human node.

        If the node is online, the handler is invoked asynchronously. If the
        node is offline or the handler raises, the message is stored in the
        inbox for later retrieval. This method never blocks agent work.
        """
        async with self._lock:
            presence = self._nodes.get(node_id)
            if presence is None:
                return False

            if presence.online and presence.handler is not None:
                handler = presence.handler
            else:
                self._enqueue(presence, message)
                self._save_inbox(node_id)
                return True

        try:
            await handler(message)
            return True
        except Exception:
            await self._return_to_inbox(node_id, message)
            return False

    def status(self) -> dict[str, dict[str, Any]]:
        """Return presence and inbox status for every human node."""
        return {
            node_id: {
                "online": presence.online,
                "inbox_size": len(presence.inbox),
                "last_seen": (
                    presence.last_seen.isoformat() if presence.last_seen else None
                ),
                "handler_registered": presence.handler is not None,
            }
            for node_id, presence in self._nodes.items()
        }

    async def get_inbox(self, node_id: str) -> list[ArgusMessage]:
        """Return all messages currently stored in a node's inbox."""
        async with self._lock:
            presence = self._nodes.get(node_id)
            if presence is None:
                return []
            return list(presence.inbox)

    async def clear_inbox(self, node_id: str) -> int:
        """Clear a node's inbox and return the number of removed messages."""
        async with self._lock:
            presence = self._nodes.get(node_id)
            if presence is None:
                return 0
            count = len(presence.inbox)
            presence.inbox.clear()
            return count

    def _enqueue(self, presence: HumanPresence, message: ArgusMessage) -> None:
        """Store a message in the inbox, respecting the size limit."""
        if len(presence.inbox) >= self._max_inbox_size:
            presence.inbox.popleft()
        presence.inbox.append(message)

    async def _enqueue_and_save(self, node_id: str, message: ArgusMessage) -> None:
        """Thread-safe enqueue plus persistence."""
        async with self._lock:
            presence = self._nodes.get(node_id)
            if presence is not None:
                self._enqueue(presence, message)
        self._save_inbox(node_id)

    async def _return_to_inbox(
        self,
        node_id: str,
        message: ArgusMessage,
    ) -> None:
        """Put a message back into the inbox after a failed delivery attempt."""
        async with self._lock:
            presence = self._nodes.get(node_id)
            if presence is not None:
                presence.online = False
                presence.handler = None
                self._enqueue(presence, message)
        self._save_inbox(node_id)

    def _inbox_path(self, node_id: str) -> Path | None:
        """Return the persisted inbox path for a node, or None if not persisted."""
        if self._storage_dir is None:
            return None
        return self._storage_dir / f"{node_id}.inbox.json"

    def _load_all_inboxes(self) -> None:
        """Load persisted inbox messages for all known human nodes."""
        if self._storage_dir is None:
            return
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        for node_id in self._nodes:
            self._load_inbox(node_id)

    def _load_inbox(self, node_id: str) -> None:
        """Load a single node's inbox from disk."""
        path = self._inbox_path(node_id)
        if path is None or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            presence = self._nodes.get(node_id)
            if presence is None:
                return
            messages = [ArgusMessage.from_dict(m) for m in data.get("messages", [])]
            presence.inbox.clear()
            for message in messages[-self._max_inbox_size :]:
                presence.inbox.append(message)
        except Exception:
            # If the persisted file is corrupt, start with an empty inbox.
            pass

    def _save_inbox(self, node_id: str) -> None:
        """Persist a node's inbox to disk."""
        path = self._inbox_path(node_id)
        if path is None:
            return
        try:
            presence = self._nodes.get(node_id)
            if presence is None:
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "node_id": node_id,
                "messages": [msg.to_dict() for msg in presence.inbox],
            }
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            # Persistence is best-effort; delivery must not fail because of IO.
            pass
