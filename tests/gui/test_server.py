"""Tests for the Argus GUI backend API."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx
import pytest

from argus.config.schema import ArgusConfig
from argus.core.bus import ArgusBus
from argus.core.orchestrator import ArgusOrchestrator
from argus.core.tree import CollaborationTree
from argus.gui.server import make_app
from argus.memory.store import MemoryStore


class FakeAgent:
    """Minimal agent that echoes a private response to avoid broadcast loops."""

    def __init__(self, node, bus: ArgusBus) -> None:
        self.node = node
        self.bus = bus
        self.tree: CollaborationTree | None = None

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def is_running(self) -> bool:
        return True

    def status(self) -> dict[str, Any]:
        return {"node_id": self.node.id, "running": True}

    async def send_to_agent(self, text: str) -> None:
        # Ignore broadcast messages to prevent reply loops between fake agents.
        if text.startswith("[group from:"):
            return
        match = re.match(r"\[from: ([^\]]+)\]", text)
        sender = match.group(1) if match else None
        if sender and sender != self.node.id:
            self.bus.send_private(self.node.id, sender, f"reply to: {text[:30]}")


@pytest.fixture
async def client(tmp_path: Path):
    config = ArgusConfig()
    config.argus.memory_dir = str(tmp_path / "memory")
    config.argus.collaboration_tree = str(tmp_path / "tree.yaml")

    tree = CollaborationTree.from_dict(
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
    memory = MemoryStore(tmp_path / "memory")
    shared_bus = ArgusBus(tree=tree)

    orch = ArgusOrchestrator(
        config=config,
        tree=tree,
        memory_store=memory,
        agent_factory=lambda node: FakeAgent(node, shared_bus),
    )
    # Replace the orchestrator bus so the fake agents and router share the same instance.
    orch.bus = shared_bus
    orch.router.bus = shared_bus
    await orch.start()

    app = make_app(orch)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    await orch.stop()


async def test_get_tree(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/tree")
    assert response.status_code == 200
    data = response.json()
    assert len(data["nodes"]) == 3
    assert data["nodes"][0]["id"] == "human"


async def test_get_nodes(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/nodes")
    assert response.status_code == 200
    nodes = response.json()
    assert {n["id"] for n in nodes} == {"human", "dev", "writer"}


async def test_get_node_status(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/nodes/dev/status")
    assert response.status_code == 200
    assert response.json()["running"] is True


async def test_send_and_receive_message(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/messages",
        json={"from_id": "human", "to": ["dev"], "text": "hello dev"},
    )
    assert response.status_code == 200
    msg = response.json()
    assert msg["from_id"] == "human"
    assert msg["to"] == ["dev"]

    response = await client.get("/api/messages/dev")
    assert response.status_code == 200
    messages = response.json()
    assert any(m["text"] == "hello dev" for m in messages)


async def test_meeting_lifecycle(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/meetings",
        json={"organizer": "human", "participants": ["human", "dev", "writer"], "topic": "设计评审"},
    )
    assert response.status_code == 200
    meeting = response.json()
    assert meeting["topic"] == "设计评审"
    assert meeting["organizer"] == "human"
    assert set(meeting["participants"]) == {"human", "dev", "writer"}

    meeting_id = meeting["id"]
    response = await client.get(f"/api/meetings/{meeting_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "running"

    response = await client.post(f"/api/meetings/{meeting_id}/close")
    assert response.status_code == 200
    assert response.json()["status"] == "closed"
