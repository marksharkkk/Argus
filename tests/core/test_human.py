"""Tests for human-node presence and inbox management."""

from __future__ import annotations

import asyncio

import pytest

from argus.core.human import HumanNodeManager
from argus.core.message import ArgusMessage, make_private_message
from argus.core.tree import CollaborationTree


@pytest.fixture
def tree() -> CollaborationTree:
    return CollaborationTree.from_dict(
        {
            "nodes": [
                {"id": "pm", "label": "PM", "type": "human"},
                {"id": "techlead", "label": "Tech Lead", "type": "human"},
                {"id": "dev", "label": "Developer", "type": "agent", "agent_id": "dev"},
            ],
            "edges": [
                {"from": "pm", "to": "dev", "bidirectional": True},
                {"from": "techlead", "to": "dev", "bidirectional": True},
            ],
        }
    )


@pytest.fixture
def manager(tree: CollaborationTree) -> HumanNodeManager:
    return HumanNodeManager(tree=tree)


async def test_offline_message_goes_to_inbox(manager: HumanNodeManager) -> None:
    """Messages delivered while offline are stored for later retrieval."""
    message = make_private_message("dev", "pm", "Need your approval on the spec.")

    ok = await manager.deliver("pm", message)

    assert ok is True
    inbox = await manager.get_inbox("pm")
    assert len(inbox) == 1
    assert inbox[0].text == "Need your approval on the spec."


async def test_online_message_reaches_handler(manager: HumanNodeManager) -> None:
    """Messages delivered while online are passed to the registered handler."""
    received: list[ArgusMessage] = []

    async def handler(message: ArgusMessage) -> None:
        received.append(message)

    await manager.register_handler("pm", handler)
    message = make_private_message("dev", "pm", "Approved, proceed.")

    ok = await manager.deliver("pm", message)

    assert ok is True
    await asyncio.sleep(0)
    assert len(received) == 1
    assert received[0].text == "Approved, proceed."
    assert await manager.get_inbox("pm") == []


async def test_register_handler_drains_pending_inbox(manager: HumanNodeManager) -> None:
    """Going online flushes any messages that arrived while offline."""
    received: list[ArgusMessage] = []

    async def handler(message: ArgusMessage) -> None:
        received.append(message)

    offline_msg = make_private_message("dev", "pm", "First")
    await manager.deliver("pm", offline_msg)

    await manager.register_handler("pm", handler)
    await asyncio.sleep(0)

    assert len(received) == 1
    assert received[0].text == "First"


async def test_multiple_human_nodes_have_isolated_inboxes(
    manager: HumanNodeManager,
) -> None:
    """Each human node maintains its own inbox."""
    await manager.deliver("pm", make_private_message("dev", "pm", "PM note"))
    await manager.deliver(
        "techlead", make_private_message("dev", "techlead", "Tech note")
    )

    assert len(await manager.get_inbox("pm")) == 1
    assert len(await manager.get_inbox("techlead")) == 1
    assert (await manager.get_inbox("pm"))[0].text == "PM note"
    assert (await manager.get_inbox("techlead"))[0].text == "Tech note"


async def test_unregister_marks_node_offline(manager: HumanNodeManager) -> None:
    """Unregistering a handler stops real-time delivery."""
    received: list[ArgusMessage] = []

    async def handler(message: ArgusMessage) -> None:
        received.append(message)

    await manager.register_handler("pm", handler)
    await manager.unregister_handler("pm")

    await manager.deliver("pm", make_private_message("dev", "pm", "After logout"))
    await asyncio.sleep(0)

    assert len(received) == 0
    assert len(await manager.get_inbox("pm")) == 1


async def test_status_reflects_presence(manager: HumanNodeManager) -> None:
    """status() reports online state and inbox size per node."""
    async def handler(message: ArgusMessage) -> None:
        pass

    await manager.register_handler("pm", handler)
    await manager.deliver("techlead", make_private_message("dev", "techlead", "x"))

    status = manager.status()
    assert status["pm"]["online"] is True
    assert status["pm"]["inbox_size"] == 0
    assert status["techlead"]["online"] is False
    assert status["techlead"]["inbox_size"] == 1


async def test_clear_inbox(manager: HumanNodeManager) -> None:
    """clear_inbox removes all stored messages."""
    await manager.deliver("pm", make_private_message("dev", "pm", "1"))
    await manager.deliver("pm", make_private_message("dev", "pm", "2"))

    count = await manager.clear_inbox("pm")

    assert count == 2
    assert await manager.get_inbox("pm") == []
