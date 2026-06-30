"""Argus Gateway orchestrator.

The ``ArgusOrchestrator`` wires together the message bus, router, agent nodes
and human handlers, and exposes the lifecycle hooks used by the CLI and GUI.
"""

from __future__ import annotations

import asyncio
import json
import signal
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from argus.adapters.mock_agent import MockAgentNode
from argus.adapters.nanobot_agent import NanobotAgentNode
from argus.config.schema import ArgusConfig
from argus.core.bus import ArgusBus
from argus.core.human import HumanHandler, HumanNodeManager
from argus.core.message import ArgusMessage
from argus.core.router import MessageRouter
from argus.core.tree import CollaborationTree, Node
from argus.memory.store import MemoryStore

AgentFactory = Callable[[Node], NanobotAgentNode]


class ArgusOrchestrator:
    """Central orchestrator for an Argus collaboration session."""

    def __init__(
        self,
        config: ArgusConfig,
        tree: CollaborationTree,
        memory_store: MemoryStore | None = None,
        workspace: Path | None = None,
        status_dir: Path | None = None,
        agent_factory: AgentFactory | None = None,
        health_check_interval: float = 10.0,
        mock: bool = False,
    ) -> None:
        self.config = config
        self.tree = tree
        self.memory_store = memory_store
        self.workspace = workspace or config.workspace_path
        self.status_dir = status_dir or self._default_status_dir()
        self._health_check_interval = health_check_interval
        self._mock = mock

        self.bus = ArgusBus(tree=tree)
        self.human_manager = HumanNodeManager(
            tree=tree,
            storage_dir=self._default_human_inbox_dir(),
        )
        self.router = MessageRouter(tree, self.bus, human_manager=self.human_manager)
        self._agent_factory = agent_factory or (
            self._mock_agent_factory if mock else self._default_agent_factory
        )
        self._agents: dict[str, NanobotAgentNode] = {}
        self._registered_human_handlers: set[str] = set()

        self._health_task: asyncio.Task[Any] | None = None
        self._shutdown_event: asyncio.Event | None = None
        self._running = False
        self._gui_server: Any | None = None

        self._build_agents()

    def _default_status_dir(self) -> Path:
        """Derive the status directory from the configured memory directory."""
        memory_dir = Path(self.config.argus.memory_dir).expanduser()
        return memory_dir.parent

    def _default_human_inbox_dir(self) -> Path:
        """Derive the human inbox directory from the configured memory directory."""
        memory_dir = Path(self.config.argus.memory_dir).expanduser()
        return memory_dir / "human_inboxes"

    def _default_agent_factory(self, node: Node) -> NanobotAgentNode:
        """Create a real nanobot-backed agent node."""
        return NanobotAgentNode(
            node=node,
            tree=self.tree,
            argus_bus=self.bus,
            config=self.config,
            workspace=self.workspace,
        )

    def _mock_agent_factory(self, node: Node) -> MockAgentNode:
        """Create a mock agent node for smoke testing."""
        return MockAgentNode(
            node=node,
            tree=self.tree,
            argus_bus=self.bus,
            config=self.config,
            workspace=self.workspace,
        )

    def _build_agents(self) -> None:
        """Instantiate an agent node adapter for every agent in the tree."""
        for node in self.tree.nodes:
            if node.type == "agent":
                self._agents[node.id] = self._agent_factory(node)
                self.router.register_agent_node(node.id, self._agents[node.id])
                logger.debug("Registered agent node {}", node.id)

    def register_human_handler(self, node_id: str, handler: HumanHandler) -> None:
        """Register a message handler for a human node and mark it online."""
        node = self.tree.get_node(node_id)
        if node is None:
            raise ValueError(f"Unknown human node: {node_id}")
        if node.type != "human":
            raise ValueError(f"Node {node_id} is not a human node")
        self._registered_human_handlers.add(node_id)
        asyncio.create_task(self.human_manager.register_handler(node_id, handler))
        self.router.register_human_handler(node_id, handler)
        logger.debug("Registered human handler for {}", node_id)

    def unregister_human_handler(self, node_id: str) -> None:
        """Mark a human node as offline; messages will go to its inbox."""
        if self.tree.get_node(node_id) is None:
            raise ValueError(f"Unknown human node: {node_id}")
        self._registered_human_handlers.discard(node_id)
        asyncio.create_task(self.human_manager.unregister_handler(node_id))
        self.router.unregister_human_handler(node_id)
        logger.debug("Unregistered human handler for {}", node_id)

    async def start(self) -> None:
        """Start the bus, router, agents and health-check loop."""
        if self._running:
            return

        self._running = True
        self._shutdown_event = asyncio.Event()

        await self.router.start()
        logger.info("ArgusOrchestrator: message router started")

        for node_id, agent in self._agents.items():
            try:
                await agent.start()
                logger.info("Started agent node {}", node_id)
            except Exception:
                logger.exception("Failed to start agent node {}", node_id)

        self._health_task = asyncio.create_task(self._health_check_loop())
        logger.info("ArgusOrchestrator: health-check loop started")

    async def stop(self) -> None:
        """Gracefully stop agents, router and background tasks."""
        if not self._running:
            return

        self._running = False

        if self._health_task is not None:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None

        for node_id, agent in list(self._agents.items()):
            try:
                await agent.stop()
                logger.info("Stopped agent node {}", node_id)
            except Exception:
                logger.exception("Failed to stop agent node {}", node_id)

        await self.router.stop()
        logger.info("ArgusOrchestrator: message router stopped")

        self._archive_session()

        if self._shutdown_event is not None:
            self._shutdown_event.set()

    async def run(self) -> None:
        """Run until a shutdown signal is received."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.request_shutdown)
            except (ValueError, NotImplementedError):
                logger.debug("Cannot register signal handler for {}", sig)

        await self.start()
        await self.start_gui_server()
        if self._shutdown_event is not None:
            await self._shutdown_event.wait()
        await self.stop_gui_server()
        await self.stop()

    def request_shutdown(self) -> None:
        """Signal the orchestrator to shut down gracefully."""
        logger.info("Shutdown requested")
        if self._shutdown_event is not None:
            self._shutdown_event.set()

    @property
    def is_running(self) -> bool:
        """Return True if the orchestrator has been started."""
        return self._running

    @property
    def shutdown_event(self) -> asyncio.Event | None:
        """Return the internal shutdown event, if any."""
        return self._shutdown_event

    def status(self) -> dict[str, dict[str, Any]]:
        """Return the current status of every node in the tree."""
        human_status = self.human_manager.status()
        result: dict[str, dict[str, Any]] = {}
        for node in self.tree.nodes:
            if node.type == "agent":
                agent = self._agents.get(node.id)
                if agent:
                    result[node.id] = agent.status()
                else:
                    result[node.id] = {
                        "node_id": node.id,
                        "label": node.label,
                        "type": "agent",
                        "running": False,
                        "inbound_queue_size": 0,
                        "outbound_queue_size": 0,
                        "session_count": 0,
                    }
            else:
                presence = human_status.get(node.id, {})
                # Human nodes share the same status schema as agents so the GUI
                # can render a single table without special-casing rows.
                result[node.id] = {
                    "node_id": node.id,
                    "label": node.label,
                    "type": "human",
                    "running": presence.get("online", False),
                    "inbound_queue_size": presence.get("inbox_size", 0),
                    "outbound_queue_size": 0,
                    "session_count": 0,
                    "handler_registered": node.id in self._registered_human_handlers,
                    "online": presence.get("online", False),
                    "last_seen": presence.get("last_seen"),
                }
        return result

    async def _health_check_loop(self) -> None:
        """Periodically log status and write a status snapshot to disk."""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                snapshot = self.status()
                self._write_status(snapshot)
                logger.debug("Health check: {} nodes reported", len(snapshot))
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Health-check loop error")

    def _write_status(self, snapshot: dict[str, dict[str, Any]]) -> None:
        """Persist a status snapshot for external status commands."""
        try:
            self.status_dir.mkdir(parents=True, exist_ok=True)
            path = self.status_dir / "status.json"
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "running": self._running,
                "nodes": snapshot,
            }
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            logger.exception("Failed to write status snapshot")

    def _archive_session(self) -> None:
        """Archive a lightweight session marker when memory store is available."""
        if self.memory_store is None:
            return
        try:
            self.memory_store.append_lesson(
                {
                    "title": "Gateway session shutdown",
                    "category": "System",
                    "content": f"Argus gateway stopped at {datetime.now(timezone.utc).isoformat()}.",
                }
            )
            logger.info("Archived session marker to memory store")
        except Exception:
            logger.exception("Failed to archive session marker")

    # ------------------------------------------------------------------
    # GUI backend hook points (Phase 17)
    # ------------------------------------------------------------------
    async def start_gui_server(self, host: str | None = None, port: int | None = None) -> None:
        """Start the GUI backend HTTP/WebSocket server."""
        from argus.gui.server import start_gui_server as _start_gui_server

        host = host or self.config.argus.api_host
        port = port or self.config.argus.api_port
        if self._gui_server is not None:
            logger.info("GUI backend server already running")
            return
        self._gui_server = _start_gui_server(self, host, port)
        await self._gui_server.start()
        logger.info("GUI backend server started at http://{}:{}", host, port)

    async def stop_gui_server(self) -> None:
        """Stop the GUI backend server."""
        if self._gui_server is None:
            return
        await self._gui_server.stop()
        self._gui_server = None
        logger.info("GUI backend server stopped")
