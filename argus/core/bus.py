"""Argus async message bus."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from argus.core.message import ArgusMessage, make_group_message, make_private_message
from argus.core.tree import CollaborationTree, parse_mentions

logger = logging.getLogger(__name__)


class ArgusBus:
    """Async message bus for routing Argus messages between nodes.

    When a ``CollaborationTree`` is supplied, the bus validates private
    messages against tree edges and filters group messages by reachability
    and ``@mention`` tags. Without a tree the bus keeps the original
    unvalidated behaviour for test scenarios.
    """

    def __init__(self, tree: CollaborationTree | None = None) -> None:
        self.tree = tree
        self._queues: dict[str, asyncio.Queue[ArgusMessage]] = {}
        self._callbacks: dict[str, set[Callable[[ArgusMessage], Awaitable[None]]]] = {}
        self._global_callbacks: set[Callable[[ArgusMessage], Awaitable[None]]] = set()
        self._lock = asyncio.Lock()

    async def register_node(self, node_id: str) -> None:
        """Create a message queue for a node."""
        async with self._lock:
            if node_id not in self._queues:
                self._queues[node_id] = asyncio.Queue()
            if node_id not in self._callbacks:
                self._callbacks[node_id] = set()

    async def unregister_node(self, node_id: str) -> None:
        """Remove a node's queue and callbacks."""
        async with self._lock:
            self._queues.pop(node_id, None)
            self._callbacks.pop(node_id, None)

    async def subscribe(
        self,
        node_id: str,
        callback: Callable[[ArgusMessage], Awaitable[None]],
    ) -> None:
        """Register an async callback for a node."""
        async with self._lock:
            if node_id not in self._queues:
                self._queues[node_id] = asyncio.Queue()
            if node_id not in self._callbacks:
                self._callbacks[node_id] = set()
            self._callbacks[node_id].add(callback)

    async def unsubscribe(
        self,
        node_id: str,
        callback: Callable[[ArgusMessage], Awaitable[None]],
    ) -> None:
        """Remove a callback from a node."""
        async with self._lock:
            if node_id in self._callbacks:
                self._callbacks[node_id].discard(callback)

    async def subscribe_global(
        self,
        callback: Callable[[ArgusMessage], Awaitable[None]],
    ) -> None:
        """Register a callback that is invoked once for every dispatched message.

        Global callbacks are useful for central routing components that need to
        observe all traffic without being subscribed to each node individually.
        """
        async with self._lock:
            self._global_callbacks.add(callback)

    async def unsubscribe_global(
        self,
        callback: Callable[[ArgusMessage], Awaitable[None]],
    ) -> None:
        """Remove a global callback."""
        async with self._lock:
            self._global_callbacks.discard(callback)

    def send_private(
        self,
        from_id: str,
        to_id: str,
        text: str,
        **kwargs: Any,
    ) -> ArgusMessage:
        """Create and dispatch a private message."""
        message = make_private_message(from_id, to_id, text, **kwargs)
        if self._can_send_private(from_id, to_id, message):
            asyncio.create_task(self.dispatch(message))
        return message

    def send_group(
        self,
        from_id: str,
        text: str,
        to: list[str] | None = None,
        skip_mention_filter: bool = False,
        **kwargs: Any,
    ) -> ArgusMessage:
        """Create and dispatch a group message."""
        recipients = self._compute_group_recipients(from_id, text, to, skip_mention_filter)
        message = make_group_message(from_id, text, recipients, **kwargs)
        if self.tree is not None and not recipients:
            logger.warning(
                "Dropping group message from %s: no reachable recipients match the targets",
                from_id,
            )
            message.metadata["delivery_blocked"] = "no reachable recipients"
        else:
            asyncio.create_task(self.dispatch(message))
        return message

    async def send_private_async(
        self,
        from_id: str,
        to_id: str,
        text: str,
        **kwargs: Any,
    ) -> ArgusMessage:
        """Create and dispatch a private message, awaiting delivery."""
        message = make_private_message(from_id, to_id, text, **kwargs)
        if self._can_send_private(from_id, to_id, message):
            await self.dispatch(message)
        return message

    async def send_group_async(
        self,
        from_id: str,
        text: str,
        to: list[str] | None = None,
        skip_mention_filter: bool = False,
        **kwargs: Any,
    ) -> ArgusMessage:
        """Create and dispatch a group message, awaiting delivery."""
        recipients = self._compute_group_recipients(from_id, text, to, skip_mention_filter)
        message = make_group_message(from_id, text, recipients, **kwargs)
        if self.tree is not None and not recipients:
            logger.warning(
                "Dropping group message from %s: no reachable recipients match the targets",
                from_id,
            )
            message.metadata["delivery_blocked"] = "no reachable recipients"
        else:
            await self.dispatch(message)
        return message

    async def dispatch(self, message: ArgusMessage) -> None:
        """Deliver a message to target queues and schedule callbacks."""
        async with self._lock:
            targets = list(message.to) if message.to else list(self._queues.keys())
            for node_id in targets:
                queue = self._queues.get(node_id)
                if queue is not None:
                    await queue.put(message)
            # Collect (node_id, callback) pairs so a callback subscribed to
            # multiple nodes is invoked once per relevant node, while a callback
            # subscribed to the same node multiple times is still deduplicated
            # because ``_callbacks[node_id]`` is a set.
            callbacks_to_invoke: list[tuple[str, Callable[[ArgusMessage], Awaitable[None]]]] = []
            seen: set[tuple[str, Callable[[ArgusMessage], Awaitable[None]]]] = set()
            for node_id in targets:
                for callback in self._callbacks.get(node_id, set()):
                    key = (node_id, callback)
                    if key not in seen:
                        seen.add(key)
                        callbacks_to_invoke.append(key)
            # Global callbacks observe every message exactly once.
            global_callbacks = list(self._global_callbacks)

        for _node_id, callback in callbacks_to_invoke:
            asyncio.create_task(callback(message))
        for callback in global_callbacks:
            asyncio.create_task(callback(message))

    def get_queue(self, node_id: str) -> asyncio.Queue[ArgusMessage]:
        """Return the message queue for a node."""
        return self._queues[node_id]

    async def get_next(self, node_id: str) -> ArgusMessage:
        """Wait for the next message for a node."""
        return await self._queues[node_id].get()

    def _can_send_private(self, from_id: str, to_id: str, message: ArgusMessage) -> bool:
        """Return True if a private message may be dispatched."""
        if self.tree is None:
            return True
        if self.tree.can_communicate(from_id, to_id):
            return True
        logger.warning(
            "Dropping private message from %s to %s: communication not allowed",
            from_id,
            to_id,
        )
        message.metadata["delivery_blocked"] = "communication not allowed"
        return False

    def _compute_group_recipients(
        self,
        from_id: str,
        text: str,
        to: list[str] | None,
        skip_mention_filter: bool = False,
    ) -> list[str]:
        """Compute the final recipient list for a group message."""
        if self.tree is None:
            return list(to) if to else []

        reachable = set(self.tree.get_reachable_nodes(from_id))

        if not to or "all" in to:
            recipients = reachable
        else:
            recipients = reachable.intersection(to)

        if not skip_mention_filter:
            mentions = parse_mentions(text)
            if mentions and "all" not in mentions:
                recipients = recipients.intersection(mentions)

        return sorted(recipients)
