"""End-to-end test for private messaging over a collaboration tree."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from argus.config.schema import ArgusConfig
from argus.core.bus import ArgusBus
from argus.core.message import ArgusMessage
from argus.core.orchestrator import ArgusOrchestrator
from argus.core.tree import CollaborationTree, Node


class FakeAgent:
    """Lightweight agent stand-in that records deliveries and can reply."""

    def __init__(self, node: Node, bus: ArgusBus) -> None:
        self.node = node
        self.bus = bus
        self.received: list[str] = []
        self._running = False

    async def start(self) -> None:
        self._running = True
        await self.bus.register_node(self.node.id)

    async def stop(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def status(self) -> dict[str, Any]:
        return {"node_id": self.node.id, "running": self._running}

    async def send_to_agent(self, text: str) -> None:
        self.received.append(text)
        # Simulate dev forwarding a private message to writer after hearing from human.
        if self.node.id == "dev" and "[from: human]" in text:
            self.bus.send_private(self.node.id, "writer", "dev forwarding to writer")


@pytest.fixture
def tree() -> CollaborationTree:
    return CollaborationTree.from_dict(
        {
            "nodes": [
                {"id": "human", "label": "Human", "type": "human"},
                {
                    "id": "dev",
                    "label": "Developer",
                    "type": "agent",
                    "agent_id": "dev-agent",
                },
                {
                    "id": "writer",
                    "label": "Writer",
                    "type": "agent",
                    "agent_id": "writer-agent",
                },
            ],
            "edges": [
                {"from": "human", "to": "dev", "bidirectional": True},
                {"from": "human", "to": "writer", "bidirectional": True},
                {"from": "dev", "to": "writer", "bidirectional": True},
            ],
        }
    )


@pytest.fixture
async def orchestrator(tree: CollaborationTree, tmp_path: Path):
    config = ArgusConfig()
    config.argus.memory_dir = str(tmp_path / "memory")

    shared_bus = ArgusBus(tree=tree)

    def agent_factory(node: Node) -> FakeAgent:
        return FakeAgent(node, shared_bus)

    orch = ArgusOrchestrator(
        config=config,
        tree=tree,
        memory_store=None,
        status_dir=tmp_path / "status",
        agent_factory=agent_factory,
        health_check_interval=60.0,
    )
    orch.bus = shared_bus
    orch.router.bus = shared_bus

    yield orch

    if orch.is_running:
        await orch.stop()


async def test_private_chat_routing(orchestrator: ArgusOrchestrator, tree: CollaborationTree) -> None:
    """Human privately chats dev; dev then privately chats writer."""
    human_messages: list[ArgusMessage] = []

    async def human_handler(message: ArgusMessage) -> None:
        human_messages.append(message)

    orchestrator.register_human_handler("human", human_handler)
    await orchestrator.start()

    # Human sends a private message to dev.
    await orchestrator.bus.send_private_async("human", "dev", "hello dev")

    # Verify dev received the message via the router/agent adapter.
    dev_agent = orchestrator._agents["dev"]

    async def _wait_for_dev() -> None:
        deadline = asyncio.get_event_loop().time() + 1.0
        while asyncio.get_event_loop().time() < deadline:
            if any("hello dev" in text for text in dev_agent.received):
                return
            await asyncio.sleep(0.01)
        raise TimeoutError("dev did not receive hello dev")

    await _wait_for_dev()
    assert any("hello dev" in text for text in dev_agent.received)

    # Dev's reply should be routed to writer.
    writer_agent = orchestrator._agents["writer"]

    async def _wait_for_writer() -> None:
        deadline = asyncio.get_event_loop().time() + 1.0
        while asyncio.get_event_loop().time() < deadline:
            if any("dev forwarding to writer" in text for text in writer_agent.received):
                return
            await asyncio.sleep(0.01)
        raise TimeoutError("writer did not receive forwarded message")

    await _wait_for_writer()
    assert any("dev forwarding to writer" in text for text in writer_agent.received)

    # Verify the collaboration tree allowed both private channels.
    assert tree.can_communicate("human", "dev")
    assert tree.can_communicate("dev", "writer")

    await orchestrator.stop()
