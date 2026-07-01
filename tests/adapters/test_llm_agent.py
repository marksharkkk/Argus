"""Tests for the real LLM agent adapter."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from argus.adapters.llm_agent import LLMAgentNode
from argus.config.schema import ArgusConfig
from argus.core.bus import ArgusBus
from argus.core.message import ArgusMessage
from argus.core.tree import CollaborationTree


@pytest.fixture
def tree(tmp_path: Path) -> CollaborationTree:
    return CollaborationTree.from_dict(
        {
            "nodes": [
                {"id": "human", "type": "human", "label": "Human"},
                {
                    "id": "dev",
                    "type": "agent",
                    "label": "Dev",
                    "agent_id": "dev",
                    "model": "deepseek/deepseek-v4-flash",
                },
            ],
            "edges": [
                {"from": "human", "to": "dev", "bidirectional": True},
            ],
        }
    )


@pytest.fixture
def config(tmp_path: Path) -> ArgusConfig:
    return ArgusConfig(
        workspace=str(tmp_path),
        providers={
            "deepseek": {
                "api_key": "sk-test",
                "api_base": "https://api.deepseek.com/v1",
            }
        },
        agents={
            "defaults": {"model": "deepseek/deepseek-v4-flash", "provider": "deepseek"}
        },
    )


@pytest.fixture
def bus(tree: CollaborationTree) -> ArgusBus:
    return ArgusBus(tree=tree)


async def _wait_for_messages(
    received: list[ArgusMessage],
    expected_count: int,
    timeout: float = 2.0,
) -> None:
    """Wait until the expected number of messages has been received."""
    deadline = asyncio.get_event_loop().time() + timeout
    while len(received) < expected_count:
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError(
                f"expected {expected_count} messages, got {len(received)}"
            )
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_llm_agent_sends_private_reply_via_tool_call(
    tree: CollaborationTree,
    config: ArgusConfig,
    bus: ArgusBus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The LLM adapter should call the LLM, parse the tool call, and route a message."""
    agent = LLMAgentNode(
        node=tree.get_node("dev"),
        tree=tree,
        argus_bus=bus,
        config=config,
        workspace=tmp_path,
    )

    mock_client = MagicMock()
    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.type = "function"
    tool_call.function.name = "argus_send_message"
    tool_call.function.arguments = json.dumps({"to": ["human"], "text": "Hello human"})

    choice = MagicMock()
    choice.message.content = None
    choice.message.tool_calls = [tool_call]

    completion = MagicMock()
    completion.choices = [choice]

    mock_client.chat.completions.create = AsyncMock(return_value=completion)
    monkeypatch.setattr(agent, "_client", mock_client)

    received: list[ArgusMessage] = []

    async def _on_message(message: ArgusMessage) -> None:
        received.append(message)

    await bus.subscribe_global(_on_message)

    await agent.start()
    await agent.send_to_agent("[from: human] hi")
    await _wait_for_messages(received, 1)
    await agent.stop()

    assert len(received) == 1
    assert received[0].from_id == "dev"
    assert received[0].to == ["human"]
    assert received[0].text == "Hello human"


@pytest.mark.asyncio
async def test_llm_agent_rejects_unreachable_target(
    tree: CollaborationTree,
    config: ArgusConfig,
    bus: ArgusBus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool calls targeting unreachable nodes must be filtered out."""
    agent = LLMAgentNode(
        node=tree.get_node("dev"),
        tree=tree,
        argus_bus=bus,
        config=config,
        workspace=tmp_path,
    )

    mock_client = MagicMock()
    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.type = "function"
    tool_call.function.name = "argus_send_message"
    tool_call.function.arguments = json.dumps(
        {"to": ["ghost"], "text": "should not send"}
    )

    choice = MagicMock()
    choice.message.content = None
    choice.message.tool_calls = [tool_call]

    completion = MagicMock()
    completion.choices = [choice]

    mock_client.chat.completions.create = AsyncMock(return_value=completion)
    monkeypatch.setattr(agent, "_client", mock_client)

    received: list[ArgusMessage] = []

    async def _on_message(message: ArgusMessage) -> None:
        received.append(message)

    await bus.subscribe_global(_on_message)

    await agent.start()
    await agent.send_to_agent("[from: human] hi")
    await asyncio.sleep(0.2)
    await agent.stop()

    assert len(received) == 0


@pytest.mark.asyncio
async def test_llm_agent_fallback_plain_reply(
    tree: CollaborationTree,
    config: ArgusConfig,
    bus: ArgusBus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the LLM returns plain content without a tool call, send it as a private reply."""
    agent = LLMAgentNode(
        node=tree.get_node("dev"),
        tree=tree,
        argus_bus=bus,
        config=config,
        workspace=tmp_path,
    )

    mock_client = MagicMock()
    choice = MagicMock()
    choice.message.content = "Plain reply"
    choice.message.tool_calls = []

    completion = MagicMock()
    completion.choices = [choice]

    mock_client.chat.completions.create = AsyncMock(return_value=completion)
    monkeypatch.setattr(agent, "_client", mock_client)

    received: list[ArgusMessage] = []

    async def _on_message(message: ArgusMessage) -> None:
        received.append(message)

    await bus.subscribe_global(_on_message)

    await agent.start()
    await agent.send_to_agent("[from: human] hi")
    await _wait_for_messages(received, 1)
    await agent.stop()

    assert len(received) == 1
    assert received[0].text == "Plain reply"
    assert received[0].to == ["human"]
