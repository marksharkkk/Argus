"""Tests for the Argus gateway orchestrator."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from argus.config.schema import ArgusConfig
from argus.core.bus import ArgusBus
from argus.core.message import ArgusMessage
from argus.core.orchestrator import ArgusOrchestrator
from argus.core.tree import CollaborationTree, Node
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
    """Lightweight stand-in for a NanobotAgentNode."""

    def __init__(self, node: Node, bus: ArgusBus) -> None:
        self.node = node
        self.bus = bus
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def status(self) -> dict[str, Any]:
        return {
            "node_id": self.node.id,
            "label": self.node.label,
            "running": self._running,
        }


@pytest.fixture
def config(tmp_path: Path) -> ArgusConfig:
    cfg = ArgusConfig()
    cfg.argus.memory_dir = str(tmp_path / "memory")
    return cfg


@pytest.fixture
def orchestrator(
    tree: CollaborationTree, config: ArgusConfig, tmp_path: Path
) -> ArgusOrchestrator:
    memory = MemoryStore(tmp_path / "memory")
    status_dir = tmp_path / "status"

    def agent_factory(node: Node) -> FakeAgent:
        return FakeAgent(node, ArgusBus())

    orch = ArgusOrchestrator(
        config=config,
        tree=tree,
        memory_store=memory,
        status_dir=status_dir,
        agent_factory=agent_factory,
        health_check_interval=0.05,
    )
    return orch


async def test_orchestrator_creates_agents(orchestrator: ArgusOrchestrator) -> None:
    """The orchestrator instantiates an adapter for each agent node."""
    assert set(orchestrator._agents.keys()) == {"dev", "writer"}
    assert orchestrator.tree.get_node("human").type == "human"


async def test_orchestrator_lifecycle(
    orchestrator: ArgusOrchestrator, tmp_path: Path
) -> None:
    """Start/stop toggles all agent nodes and writes a status snapshot."""
    received: list[ArgusMessage] = []

    async def human_handler(message: ArgusMessage) -> None:
        received.append(message)

    orchestrator.register_human_handler("human", human_handler)

    await orchestrator.start()

    for agent in orchestrator._agents.values():
        assert agent.is_running()

    # Allow the health-check loop to write at least one snapshot.
    await asyncio.sleep(0.15)
    status_path = tmp_path / "status" / "status.json"
    assert status_path.exists()
    snapshot = json.loads(status_path.read_text(encoding="utf-8"))
    assert snapshot["running"] is True
    assert set(snapshot["nodes"].keys()) == {"human", "dev", "writer"}

    await orchestrator.stop()

    for agent in orchestrator._agents.values():
        assert not agent.is_running()


async def test_orchestrator_status(orchestrator: ArgusOrchestrator) -> None:
    """status() reports agent and human node state."""
    await orchestrator.start()
    status = orchestrator.status()

    assert status["dev"]["running"] is True
    assert status["writer"]["running"] is True
    assert status["human"]["type"] == "human"
    assert status["human"]["handler_registered"] is False

    async def noop_handler(message: ArgusMessage) -> None:
        pass

    orchestrator.register_human_handler("human", noop_handler)
    status = orchestrator.status()
    assert status["human"]["handler_registered"] is True

    await orchestrator.stop()


async def test_orchestrator_archives_session_on_stop(
    orchestrator: ArgusOrchestrator, tmp_path: Path
) -> None:
    """Stopping the orchestrator archives a session marker when memory is configured."""
    await orchestrator.start()
    await orchestrator.stop()

    lessons_path = tmp_path / "memory" / "team" / "lessons_learned.md"
    assert lessons_path.exists()
    content = lessons_path.read_text(encoding="utf-8")
    assert "Gateway session shutdown" in content
