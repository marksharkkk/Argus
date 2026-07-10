"""End-to-end test for the meeting engine over a collaboration tree."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from argus.config.schema import ArgusConfig
from argus.core.bus import ArgusBus
from argus.core.meeting import MeetingEngine
from argus.core.message import ArgusMessage
from argus.core.orchestrator import ArgusOrchestrator
from argus.core.tree import CollaborationTree, Node
from argus.memory.store import MemoryStore


class MeetingFakeAgent:
    """Agent stand-in that responds with a turn opinion when prompted."""

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
        # Respond only when the meeting engine explicitly asks for this agent's turn.
        if "现在轮到" in text and self.node.id in text:
            self.bus.send_group(
                self.node.id,
                f"{self.node.id} 认为应该使用 Python。",
                to=[],
            )


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
async def meeting_setup(tree: CollaborationTree, tmp_path: Path):
    config = ArgusConfig()
    config.argus.memory_dir = str(tmp_path / "memory")

    shared_bus = ArgusBus(tree=tree)
    memory = MemoryStore(tmp_path / "memory")

    def agent_factory(node: Node) -> MeetingFakeAgent:
        return MeetingFakeAgent(node, shared_bus)

    orch = ArgusOrchestrator(
        config=config,
        tree=tree,
        memory_store=memory,
        status_dir=tmp_path / "status",
        agent_factory=agent_factory,
        health_check_interval=60.0,
    )
    orch.bus = shared_bus
    orch.router.bus = shared_bus

    human_messages: list[ArgusMessage] = []

    async def human_handler(message: ArgusMessage) -> None:
        human_messages.append(message)

    orch.register_human_handler("human", human_handler)

    # Subscribe directly to the bus to observe messages delivered to any participant.
    bus_messages: list[ArgusMessage] = []

    async def bus_handler(message: ArgusMessage) -> None:
        bus_messages.append(message)

    for participant_id in ["human", "dev", "writer"]:
        await shared_bus.subscribe(participant_id, bus_handler)
    await orch.start()

    engine = MeetingEngine(
        bus=shared_bus,
        router=orch.router,
        memory_store=memory,
        response_timeout=5.0,
    )

    yield orch, engine, human_messages, bus_messages, memory

    for participant_id in ["human", "dev", "writer"]:
        await shared_bus.unsubscribe(participant_id, bus_handler)
    await orch.stop()


async def _wait_for_message_text(
    messages: list[ArgusMessage], text: str, timeout: float = 2.0
) -> None:
    """Poll until ``text`` appears in any message's text or ``timeout`` elapses."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if any(text in m.text for m in messages):
            return
        await asyncio.sleep(0.01)
    raise TimeoutError(f"expected {text!r} in messages")


async def _wait_for_path(path: Path, timeout: float = 1.0) -> None:
    """Poll until ``path`` exists or ``timeout`` elapses."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if path.exists():
            return
        await asyncio.sleep(0.01)
    raise TimeoutError(f"expected path to exist: {path}")


async def test_meeting_round_robin_broadcast_and_archive(
    meeting_setup: tuple[
        ArgusOrchestrator, MeetingEngine, list[ArgusMessage], list[ArgusMessage], MemoryStore
    ],
    tmp_path: Path,
) -> None:
    """Run a full meeting lifecycle through the orchestrator and verify archive."""
    orch, engine, human_messages, bus_messages, memory = meeting_setup

    meeting = await engine.start_meeting(
        organizer="human",
        participants=["human", "dev", "writer"],
        topic="技术栈选型",
    )

    assert meeting.status == "running"
    assert meeting.topic == "技术栈选型"
    assert set(meeting.participants) == {"human", "dev", "writer"}

    # Wait for fake agents to answer and broadcasts to settle.
    await _wait_for_message_text(bus_messages, "现在进入自由讨论阶段", timeout=2.0)

    # Messages targeted at human on the bus include the start notice and broadcasts.
    bus_texts = [m.text for m in bus_messages]
    assert any("会议开始：技术栈选型" in text for text in bus_texts)
    assert any("dev 认为应该使用 Python。" in text for text in bus_texts)
    assert any("writer 认为应该使用 Python。" in text for text in bus_texts)
    assert any("现在进入自由讨论阶段" in text for text in bus_texts)

    # The router delivers external messages (from dev/writer) to the human handler.
    router_texts = [m.text for m in human_messages]
    assert any("dev 认为应该使用 Python。" in text for text in router_texts)
    assert any("writer 认为应该使用 Python。" in text for text in router_texts)

    # Meeting history: start + two turn responses + free discussion.
    assert len(meeting.history) == 4
    assert meeting.history[0].text == "会议开始：技术栈选型"
    assert meeting.history[-1].text == "现在进入自由讨论阶段，参与者可以互相 @。"

    closed = await engine.close_meeting(meeting.id)
    assert closed.status == "closed"
    assert closed.closed_at is not None

    # Verify meeting archive was written to the memory store.
    archive_path = tmp_path / "memory" / "meetings" / f"{meeting.created_at:%Y-%m-%d}.md"
    await _wait_for_path(archive_path)
    content = archive_path.read_text(encoding="utf-8")
    assert "技术栈选型" in content
    assert "dev 认为应该使用 Python。" in content
    assert "writer 认为应该使用 Python。" in content
