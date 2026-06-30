"""Tests for the Argus message bus."""

from __future__ import annotations

import asyncio

import pytest

from argus.core.bus import ArgusBus
from argus.core.message import ArgusMessage
from argus.core.tree import CollaborationTree


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


@pytest.fixture
def one_way_tree() -> CollaborationTree:
    """Tree where dev can reach writer, but writer cannot reach dev."""
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
                {"from": "dev", "to": "writer", "bidirectional": False},
            ],
        }
    )


async def _drain_callbacks() -> None:
    """Yield control so callback tasks created by dispatch can run."""
    await asyncio.sleep(0.01)


async def test_dispatch_without_tree_delivers_to_targets() -> None:
    """A bus without a tree dispatches messages to explicit targets."""
    bus = ArgusBus()
    await bus.register_node("a")
    await bus.register_node("b")

    collected: list[ArgusMessage] = []

    async def handler(message: ArgusMessage) -> None:
        collected.append(message)

    await bus.subscribe("b", handler)
    await bus.send_private_async("a", "b", "hello")
    await _drain_callbacks()

    assert len(collected) == 1
    assert collected[0].text == "hello"
    assert collected[0].to == ["b"]


async def test_private_message_blocked_without_edge(one_way_tree: CollaborationTree) -> None:
    """A private message is dropped when no directed edge exists."""
    bus = ArgusBus(tree=one_way_tree)
    await bus.register_node("dev")

    collected: list[ArgusMessage] = []

    async def handler(message: ArgusMessage) -> None:
        collected.append(message)

    await bus.subscribe("dev", handler)
    message = await bus.send_private_async("writer", "dev", "unreachable")

    assert message.metadata.get("delivery_blocked")
    assert not collected


async def test_private_message_allowed_with_edge(tree: CollaborationTree) -> None:
    """A private message is delivered along an existing edge."""
    bus = ArgusBus(tree=tree)
    await bus.register_node("dev")

    collected: list[ArgusMessage] = []

    async def handler(message: ArgusMessage) -> None:
        collected.append(message)

    await bus.subscribe("dev", handler)
    await bus.send_private_async("human", "dev", "hello dev")
    await _drain_callbacks()

    assert len(collected) == 1
    assert collected[0].text == "hello dev"


async def test_group_message_reaches_all_reachable_nodes(tree: CollaborationTree) -> None:
    """A broadcast group message reaches every node reachable from the sender."""
    bus = ArgusBus(tree=tree)
    for node_id in ("dev", "writer"):
        await bus.register_node(node_id)

    collected: list[ArgusMessage] = []

    async def handler(message: ArgusMessage) -> None:
        collected.append(message)

    await bus.subscribe("dev", handler)
    await bus.subscribe("writer", handler)

    await bus.send_group_async("human", "@all 大家好")
    await _drain_callbacks()

    texts = [m.text for m in collected]
    assert texts.count("@all 大家好") == 2


async def test_group_message_filtered_by_mentions(tree: CollaborationTree) -> None:
    """Mentions restrict group delivery to the intersection of reachability and @tags."""
    bus = ArgusBus(tree=tree)
    for node_id in ("dev", "writer"):
        await bus.register_node(node_id)

    dev_messages: list[ArgusMessage] = []
    writer_messages: list[ArgusMessage] = []

    async def dev_handler(message: ArgusMessage) -> None:
        dev_messages.append(message)

    async def writer_handler(message: ArgusMessage) -> None:
        writer_messages.append(message)

    await bus.subscribe("dev", dev_handler)
    await bus.subscribe("writer", writer_handler)

    await bus.send_group_async("human", "@dev 仅开发可见")
    await _drain_callbacks()

    assert len(dev_messages) == 1
    assert dev_messages[0].text == "@dev 仅开发可见"
    assert not writer_messages


async def test_group_message_to_list_intersects_with_reachable(
    one_way_tree: CollaborationTree,
) -> None:
    """An explicit ``to`` list is intersected with reachable nodes."""
    bus = ArgusBus(tree=one_way_tree)
    for node_id in ("dev", "writer"):
        await bus.register_node(node_id)

    collected: list[ArgusMessage] = []

    async def handler(message: ArgusMessage) -> None:
        collected.append(message)

    await bus.subscribe("dev", handler)
    await bus.subscribe("writer", handler)

    # writer cannot reach dev in this tree, so the message is dropped.
    await bus.send_group_async("writer", "hello team", to=["dev"])
    await _drain_callbacks()

    assert not collected


async def test_group_message_to_list_delivers_reachable_targets(
    one_way_tree: CollaborationTree,
) -> None:
    """An explicit ``to`` list delivers only the reachable subset."""
    bus = ArgusBus(tree=one_way_tree)
    for node_id in ("dev", "writer"):
        await bus.register_node(node_id)

    collected: list[ArgusMessage] = []

    async def handler(message: ArgusMessage) -> None:
        collected.append(message)

    await bus.subscribe("dev", handler)
    await bus.subscribe("writer", handler)

    # dev can reach writer, so writer should receive it even though dev is also in ``to``.
    await bus.send_group_async("dev", "hello writer", to=["dev", "writer"])
    await _drain_callbacks()

    texts = [m.text for m in collected]
    assert texts.count("hello writer") == 1
    assert all(m.to == ["writer"] for m in collected)
