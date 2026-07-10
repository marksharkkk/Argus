"""Argus message routing engine."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from argus.core.bus import ArgusBus
from argus.core.human import HumanHandler, HumanNodeManager
from argus.core.message import ArgusMessage
from argus.core.tree import CollaborationTree

if TYPE_CHECKING:
    from argus.adapters.llm_agent import LLMAgentNode
    from argus.adapters.mock_agent import MockAgentNode

    AgentNode = MockAgentNode | LLMAgentNode

logger = logging.getLogger(__name__)


class MessageRouter:
    """Route ``ArgusMessage`` instances between agent and human nodes."""

    def __init__(
        self,
        tree: CollaborationTree,
        bus: ArgusBus,
        human_manager: HumanNodeManager | None = None,
    ) -> None:
        self.tree = tree
        self.bus = bus
        self._human_manager = human_manager
        self._agent_nodes: dict[str, AgentNode] = {}
        self._human_handlers: dict[str, HumanHandler] = {}
        self._subscribed_nodes: set[str] = set()

    def register_agent_node(self, node_id: str, agent: AgentNode) -> None:
        """Register an agent node instance for the given tree node ID."""
        self._agent_nodes[node_id] = agent

    def register_human_handler(
        self,
        node_id: str,
        handler: HumanHandler,
    ) -> None:
        """Register a callback that delivers messages to a human node."""
        self._human_handlers[node_id] = handler
        if self._human_manager is not None:
            asyncio.create_task(self._human_manager.register_handler(node_id, handler))

    def unregister_human_handler(self, node_id: str) -> None:
        """Remove the human handler and mark the node offline."""
        self._human_handlers.pop(node_id, None)
        if self._human_manager is not None:
            asyncio.create_task(self._human_manager.unregister_handler(node_id))

    async def start(self) -> None:
        """Subscribe the router once globally so it observes all traffic."""
        await self.bus.subscribe_global(self._on_message)
        self._subscribed_nodes.add("__global__")
        logger.debug("MessageRouter started globally")

    async def stop(self) -> None:
        """Unsubscribe the router from the bus."""
        if "__global__" in self._subscribed_nodes:
            await self.bus.unsubscribe_global(self._on_message)
            self._subscribed_nodes.discard("__global__")
        logger.debug("MessageRouter stopped")

    async def _on_message(self, message: ArgusMessage) -> None:
        """Internal callback invoked by the bus when a message is dispatched."""
        sender = self.tree.get_node(message.from_id)
        if sender is None:
            logger.warning("Dropping message from unknown node: %s", message.from_id)
            return

        if message.metadata.get("delivery_blocked"):
            return

        # Agent-originated group messages are UI broadcasts / replies.
        # Delivering them to other agents would trigger reply storms, so we
        # only forward them to human nodes.
        if sender.type == "agent" and message.is_group:
            for target_id in message.to:
                target = self.tree.get_node(target_id)
                if target is not None and target.type == "human":
                    await self._deliver(target_id, message)
            return

        if len(message.to) == 1:
            await self._deliver(message.to[0], message)
        else:
            for target_id in message.to:
                await self._deliver(target_id, message)

    async def _deliver(self, target_id: str, message: ArgusMessage) -> None:
        """Deliver a message to a single target node."""
        node = self.tree.get_node(target_id)
        if node is None:
            logger.warning("Unknown target node %s; ignoring message", target_id)
            return

        try:
            if node.type == "agent":
                agent = self._agent_nodes.get(target_id)
                if agent is None:
                    logger.warning(
                        "No registered agent for node %s; dropping message",
                        target_id,
                    )
                    return
                await agent.send_to_agent(self._format_message_for_agent(message))
            elif node.type == "human":
                if self._human_manager is not None:
                    await self._human_manager.deliver(target_id, message)
                else:
                    handler = self._human_handlers.get(target_id)
                    if handler is None:
                        logger.warning(
                            "No human handler for node %s; dropping message",
                            target_id,
                        )
                        return
                    await handler(message)
            else:
                logger.warning("Unsupported node type %r for %s", node.type, target_id)
        except Exception:
            logger.exception("Failed to deliver message to %s", target_id)

    def _format_message_for_agent(self, message: ArgusMessage) -> str:
        """Return a human-readable string for agent consumption."""
        if message.is_group:
            return f"[group from: {message.from_id}] {message.text}"
        return f"[from: {message.from_id}] {message.text}"
