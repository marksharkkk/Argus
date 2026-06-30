"""Mock agent adapter for smoke testing Argus without LLM providers."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from argus.config.schema import ArgusConfig
from argus.core.bus import ArgusBus
from argus.core.message import ArgusMessage
from argus.core.tree import CollaborationTree, Node, parse_mentions

logger = logging.getLogger(__name__)


class MockAgentNode:
    """A fake agent node that echoes back simple responses for testing."""

    def __init__(
        self,
        node: Node,
        tree: CollaborationTree,
        argus_bus: ArgusBus,
        config: ArgusConfig,
        workspace: Path | None = None,
    ) -> None:
        self.node = node
        self.tree = tree
        self.argus_bus = argus_bus
        self.config = config
        base_workspace = workspace or config.workspace_path
        self.workspace = base_workspace / "argus" / "nodes" / node.id
        self.workspace.mkdir(parents=True, exist_ok=True)

        self._running = False
        self._task: asyncio.Task[Any] | None = None
        self._inbox: asyncio.Queue[ArgusMessage] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._session_count = 0
        self._messages_received = 0

    async def start(self) -> None:
        async with self._lock:
            if self._running:
                return
            await self.argus_bus.register_node(self.node.id)
            self._running = True
            self._task = asyncio.create_task(self._loop())
            logger.info("Mock agent %s started", self.node.id)

    async def stop(self) -> None:
        async with self._lock:
            if not self._running:
                return
            self._running = False
            task = self._task
            self._task = None
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            logger.info("Mock agent %s stopped", self.node.id)

    async def send_to_agent(self, text: str) -> None:
        """Inject a message into the mock agent's inbox."""
        message = ArgusMessage(
            from_id="user",
            to=[self.node.id],
            text=text,
        )
        await self._inbox.put(message)

    def is_running(self) -> bool:
        return self._running

    def status(self) -> dict[str, Any]:
        return {
            "node_id": self.node.id,
            "label": self.node.label,
            "running": self.is_running(),
            "model": self.node.model or self.config.agents.defaults.model,
            "workspace": str(self.workspace),
            "session_count": self._session_count,
            "messages_received": self._messages_received,
            "tools": ["mock_reply"],
        }

    async def _loop(self) -> None:
        """Process incoming messages and reply with mock responses."""
        while self._running:
            try:
                message = await asyncio.wait_for(self._inbox.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            self._messages_received += 1
            logger.debug("Mock agent %s received: %s", self.node.id, message.text)

            reply_text = self._generate_reply(message)
            if reply_text:
                await self._send_reply(message, reply_text)

    def _extract_original_sender(self, text: str) -> str | None:
        """Parse the sender prefix added by MessageRouter, e.g. [from: human]."""
        if text.startswith("[from:"):
            end = text.find("]")
            if end != -1:
                return text[6:end].strip()
        if text.startswith("[group from:"):
            end = text.find("]")
            if end != -1:
                return text[12:end].strip()
        return None

    def _generate_reply(self, message: ArgusMessage) -> str | None:
        """Generate a deterministic mock reply."""
        text = message.text
        if text.startswith("[from:") or text.startswith("[group from:"):
            # Strip the formatted prefix added by MessageRouter.
            idx = text.find("]")
            if idx != -1:
                text = text[idx + 1 :].strip()

        prefix = f"[Mock {self.node.id}]"
        if "会议" in text or "meeting" in text.lower():
            return f"{prefix} 收到会议相关内容，我会积极参与讨论。"
        if "?" in text or "？" in text or "吗" in text:
            return f"{prefix} 这是一个很好的问题，我的看法是：可以先从最小可行方案开始。"
        return f"{prefix} 已收到消息：{text[:80]}{'...' if len(text) > 80 else ''}"

    async def _send_reply(self, incoming: ArgusMessage, text: str) -> None:
        """Send a mock reply back to reachable targets."""
        original_sender = self._extract_original_sender(incoming.text) or incoming.from_id
        if incoming.is_group:
            # In a group, reply back to the group (excluding self).
            mentions = parse_mentions(incoming.text)
            targets = self._choose_reply_targets(original_sender, mentions)
            if targets:
                self.argus_bus.send_group(
                    from_id=self.node.id,
                    text=text,
                    to=targets,
                )
        else:
            self.argus_bus.send_private(
                from_id=self.node.id,
                to_id=original_sender,
                text=text,
            )

    def _choose_reply_targets(
        self,
        sender_id: str,
        mentions: list[str],
    ) -> list[str]:
        """Choose who should receive a group reply."""
        reachable = set(self.tree.get_reachable_nodes(self.node.id))
        reachable.discard(self.node.id)
        if not reachable:
            return [sender_id]
        if mentions and "all" not in mentions:
            targets = reachable.intersection(mentions)
            if targets:
                return sorted(targets)
        return sorted(reachable)
