"""End-to-end test for group messaging with @all and @mention."""

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
    """Agent stand-in that records every routed message it receives."""

    def __init__(self, node: Node, bus: ArgusBus) -> None:
        self.node = node
        self.bus = bus
        self.received: list[ArgusMessage] = []
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


async def _wait_for_text(received: list[str], text: str, timeout: float = 1.0) -> None:
    """Poll until ``text`` appears in ``received`` or ``timeout`` elapses."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if any(text in item for item in received):
            return
        await asyncio.sleep(0.01)
    raise TimeoutError(f"expected {text!r} in received messages")


async def test_group_chat_at_all(orchestrator: ArgusOrchestrator, tree: CollaborationTree) -> None:
    """Human sends a broadcast '@all' and both reachable agents receive it."""
    human_messages: list[ArgusMessage] = []

    async def human_handler(message: ArgusMessage) -> None:
        human_messages.append(message)

    orchestrator.register_human_handler("human", human_handler)
    await orchestrator.start()

    await orchestrator.bus.send_group_async("human", "@all 大家注意一下")

    dev_agent = orchestrator._agents["dev"]
    writer_agent = orchestrator._agents["writer"]
    await _wait_for_text(dev_agent.received, "@all 大家注意一下")
    await _wait_for_text(writer_agent.received, "@all 大家注意一下")

    await orchestrator.stop()


async def test_group_chat_mentions(orchestrator: ArgusOrchestrator, tree: CollaborationTree) -> None:
    """Human sends '@dev @writer' and only the mentioned agents receive it."""
    human_messages: list[ArgusMessage] = []

    async def human_handler(message: ArgusMessage) -> None:
        human_messages.append(message)

    orchestrator.register_human_handler("human", human_handler)
    await orchestrator.start()

    await orchestrator.bus.send_group_async(
        "human", "@dev @writer 开会讨论一下", to=["dev", "writer"]
    )

    dev_agent = orchestrator._agents["dev"]
    writer_agent = orchestrator._agents["writer"]
    await _wait_for_text(dev_agent.received, "@dev @writer 开会讨论一下")
    await _wait_for_text(writer_agent.received, "@dev @writer 开会讨论一下")

    await orchestrator.stop()
