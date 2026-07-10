"""Tests for the Argus meeting engine."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from argus.core.bus import ArgusBus
from argus.core.meeting import MeetingEngine
from argus.core.message import ArgusMessage
from argus.core.router import MessageRouter
from argus.core.tree import CollaborationTree
from argus.memory.store import MemoryStore


@pytest.fixture
def tree() -> CollaborationTree:
    return CollaborationTree.from_dict(
        {
            "nodes": [
                {"id": "human", "label": "Human", "type": "human"},
                {"id": "dev", "label": "Developer", "type": "agent", "agent_id": "dev-agent"},
                {"id": "writer", "label": "Writer", "type": "agent", "agent_id": "writer-agent"},
            ],
            "edges": [
                {"from": "human", "to": "dev", "bidirectional": True},
                {"from": "human", "to": "writer", "bidirectional": True},
                {"from": "dev", "to": "writer", "bidirectional": True},
            ],
        }
    )


class FakeAgent:
    """Minimal stand-in for an agent that echoes a response via the bus."""

    def __init__(self, node_id: str, bus: ArgusBus) -> None:
        self.node_id = node_id
        self.bus = bus

    async def send_to_agent(self, text: str) -> None:
        await asyncio.sleep(0.01)
        self.bus.send_group(
            self.node_id,
            f"{self.node_id} 收到提示并回复。",
            to=[],
        )


@pytest.fixture
async def engine_with_mock_provider(tree: CollaborationTree, tmp_path: Path):
    bus = ArgusBus(tree=tree)
    router = MessageRouter(tree, bus)
    memory = MemoryStore(tmp_path / "memory")

    router_messages: list[ArgusMessage] = []

    async def human_handler(message: ArgusMessage) -> None:
        router_messages.append(message)

    router.register_human_handler("human", human_handler)
    await router.start()

    bus_messages: list[ArgusMessage] = []

    async def bus_handler(message: ArgusMessage) -> None:
        bus_messages.append(message)

    for participant_id in ["human", "dev", "writer"]:
        await bus.subscribe(participant_id, bus_handler)

    responses = {
        "dev": "我们应该使用 Python。",
        "writer": "我同意，Python 生态丰富。",
    }

    async def response_provider(
        participant_id: str, prompt: str, history: list[ArgusMessage]
    ) -> str:
        return responses[participant_id]

    meeting_engine = MeetingEngine(
        bus=bus,
        router=router,
        memory_store=memory,
        response_provider=response_provider,
    )

    yield meeting_engine, router_messages, bus_messages

    await router.stop()
    for participant_id in ["human", "dev", "writer"]:
        await bus.unsubscribe(participant_id, bus_handler)


async def test_three_person_meeting_with_response_provider(
    engine_with_mock_provider: tuple[MeetingEngine, list[ArgusMessage], list[ArgusMessage]],
    tmp_path: Path,
) -> None:
    """A three-person meeting: human organizer + two agents."""
    meeting_engine, router_messages, bus_messages = engine_with_mock_provider

    meeting = await meeting_engine.start_meeting(
        organizer="human",
        participants=["human", "dev", "writer"],
        topic="技术栈选型",
    )

    assert meeting.status == "running"
    assert meeting.topic == "技术栈选型"
    assert meeting.organizer == "human"
    assert set(meeting.participants) == {"human", "dev", "writer"}

    # Wait for the round-robin phase to finish and bus dispatches to settle.
    await asyncio.sleep(0.1)

    # Every message sent to the human node should be observable on the bus.
    bus_texts = [m.text for m in bus_messages]
    assert any("会议开始：技术栈选型" == text for text in bus_texts)
    assert any("我们应该使用 Python。" in text for text in bus_texts)
    assert any("我同意，Python 生态丰富。" in text for text in bus_texts)
    assert any("现在进入自由讨论阶段" in text for text in bus_texts)

    # The router only delivers messages from reachable nodes to the human.
    router_texts = [m.text for m in router_messages]
    assert any("我们应该使用 Python。" in text for text in router_texts)
    assert any("我同意，Python 生态丰富。" in text for text in router_texts)

    # Close the meeting and wait for the background task to exit.
    closed = await meeting_engine.close_meeting(meeting.id)
    await meeting_engine.wait_for_meeting(meeting.id)

    assert closed.status == "closed"
    assert closed.closed_at is not None
    assert bus_messages[-1].text == "会议结束。"

    # Meeting history should contain start, two responses, free discussion, and close.
    assert len(meeting.history) == 5
    assert meeting.history[0].text == "会议开始：技术栈选型"
    assert meeting.history[-2].text == "现在进入自由讨论阶段，参与者可以互相 @。"
    assert meeting.history[-1].text == "会议结束。"

    # Verify the meeting archive was written.
    archive_path = tmp_path / "memory" / "meetings" / f"{meeting.created_at:%Y-%m-%d}.md"
    assert archive_path.exists()
    content = archive_path.read_text(encoding="utf-8")
    assert "技术栈选型" in content
    assert "dev" in content
    assert "writer" in content


@pytest.fixture
async def engine_with_fake_agents(tree: CollaborationTree, tmp_path: Path):
    bus = ArgusBus(tree=tree)
    router = MessageRouter(tree, bus)
    memory = MemoryStore(tmp_path / "memory")

    human_messages: list[ArgusMessage] = []

    async def human_handler(message: ArgusMessage) -> None:
        human_messages.append(message)

    router.register_human_handler("human", human_handler)

    # Register fake agents that respond via the bus when prompted.
    router.register_agent_node("dev", FakeAgent("dev", bus))
    router.register_agent_node("writer", FakeAgent("writer", bus))

    await router.start()

    meeting_engine = MeetingEngine(
        bus=bus,
        router=router,
        memory_store=memory,
        response_timeout=5.0,
    )

    yield meeting_engine, human_messages

    await router.stop()


async def test_meeting_with_bus_response_provider(
    engine_with_fake_agents: tuple[MeetingEngine, list[ArgusMessage]],
    tmp_path: Path,
) -> None:
    """Meeting engine collects real agent responses through the ArgusBus."""
    meeting_engine, human_messages = engine_with_fake_agents

    meeting = await meeting_engine.start_meeting(
        organizer="human",
        participants=["human", "dev", "writer"],
        topic="方案评审",
    )

    assert meeting.status == "running"

    # Wait for fake agents to respond and dispatches to settle.
    await asyncio.sleep(0.1)

    # Human receives broadcasts from dev and writer.
    router_texts = [m.text for m in human_messages]
    assert any("dev 收到提示并回复。" in text for text in router_texts)
    assert any("writer 收到提示并回复。" in text for text in router_texts)

    closed = await meeting_engine.close_meeting(meeting.id)
    await meeting_engine.wait_for_meeting(meeting.id)
    assert closed.status == "closed"

    archive_path = tmp_path / "memory" / "meetings" / f"{meeting.created_at:%Y-%m-%d}.md"
    assert archive_path.exists()
    content = archive_path.read_text(encoding="utf-8")
    assert "方案评审" in content


async def test_human_takeover_skip_turn(tree: CollaborationTree, tmp_path: Path) -> None:
    """A human can skip the current agent's turn while it is being generated."""
    bus = ArgusBus(tree=tree)
    router = MessageRouter(tree, bus)
    memory = MemoryStore(tmp_path / "memory")

    human_messages: list[ArgusMessage] = []

    async def human_handler(message: ArgusMessage) -> None:
        human_messages.append(message)

    router.register_human_handler("human", human_handler)
    await router.start()

    dev_started = asyncio.Event()

    async def response_provider(
        participant_id: str, prompt: str, history: list[ArgusMessage]
    ) -> str:
        if participant_id == "dev":
            dev_started.set()
            await asyncio.sleep(3600)  # Simulate a very slow agent.
            return "dev slow response"
        return f"{participant_id} response"

    meeting_engine = MeetingEngine(
        bus=bus,
        router=router,
        memory_store=memory,
        response_provider=response_provider,
    )

    meeting = await meeting_engine.start_meeting(
        organizer="human",
        participants=["human", "dev", "writer"],
        topic="human takeover",
    )

    await asyncio.wait_for(dev_started.wait(), timeout=1.0)
    await meeting_engine.command_meeting(meeting.id, "skip_turn")

    # Wait for the round-robin to finish (writer turn + free discussion).
    await asyncio.sleep(0.2)

    router_texts = [m.text for m in human_messages]
    assert not any("dev slow response" in text for text in router_texts)
    assert any("主持人跳过 dev 的发言" in text for text in router_texts)
    assert any("现在进入自由讨论阶段" in text for text in router_texts)

    closed = await meeting_engine.close_meeting(meeting.id)
    await meeting_engine.wait_for_meeting(meeting.id)
    assert closed.status == "closed"

    await router.stop()


async def test_human_takeover_update_topic(tree: CollaborationTree, tmp_path: Path) -> None:
    """A human can update the meeting topic while the meeting is running."""
    bus = ArgusBus(tree=tree)
    router = MessageRouter(tree, bus)
    memory = MemoryStore(tmp_path / "memory")

    human_messages: list[ArgusMessage] = []

    async def human_handler(message: ArgusMessage) -> None:
        human_messages.append(message)

    router.register_human_handler("human", human_handler)
    await router.start()

    async def response_provider(
        participant_id: str, prompt: str, history: list[ArgusMessage]
    ) -> str:
        return f"{participant_id} 收到。"

    meeting_engine = MeetingEngine(
        bus=bus,
        router=router,
        memory_store=memory,
        response_provider=response_provider,
    )

    meeting = await meeting_engine.start_meeting(
        organizer="human",
        participants=["human", "dev", "writer"],
        topic="old topic",
    )

    await asyncio.sleep(0.1)
    await meeting_engine.command_meeting(meeting.id, "update_topic", "new topic")
    await asyncio.sleep(0.05)

    assert meeting.topic == "new topic"
    router_texts = [m.text for m in human_messages]
    assert any("会议议题更新为：new topic" in text for text in router_texts)

    closed = await meeting_engine.close_meeting(meeting.id)
    await meeting_engine.wait_for_meeting(meeting.id)
    assert closed.status == "closed"

    await router.stop()
