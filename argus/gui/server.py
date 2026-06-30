"""Argus GUI backend HTTP/WebSocket server."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from argus.core.meeting import MeetingEngine
from argus.core.message import ArgusMessage
from argus.core.orchestrator import ArgusOrchestrator
from argus.core.tree import CollaborationTree


class MessagePayload(BaseModel):
    """Payload for sending a message through the ArgusBus."""

    from_id: str
    to: list[str] | None = None
    text: str


class MeetingPayload(BaseModel):
    """Payload for starting a meeting."""

    organizer: str
    participants: list[str]
    topic: str


@dataclass
class ConnectionManager:
    """Manage active WebSocket connections and broadcast messages."""

    active: list[WebSocket] = field(default_factory=list)
    node_connections: dict[str, list[WebSocket]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    message_history: list[ArgusMessage] = field(default_factory=list)
    _seen_ids: set[str] = field(default_factory=set)

    async def connect(self, websocket: WebSocket, node_id: str | None = None) -> None:
        await websocket.accept()
        async with self.lock:
            self.active.append(websocket)
            if node_id:
                self.node_connections.setdefault(node_id, []).append(websocket)

    async def disconnect(self, websocket: WebSocket, node_id: str | None = None) -> None:
        async with self.lock:
            if websocket in self.active:
                self.active.remove(websocket)
            if node_id and node_id in self.node_connections:
                if websocket in self.node_connections[node_id]:
                    self.node_connections[node_id].remove(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self.lock:
            dead: list[WebSocket] = []
            for ws in self.active:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                if ws in self.active:
                    self.active.remove(ws)
                for node_id, conns in self.node_connections.items():
                    if ws in conns:
                        conns.remove(ws)

    async def send_to_node(self, node_id: str, message: dict[str, Any]) -> None:
        """Send a message only to WebSocket connections bound to a specific node."""
        async with self.lock:
            connections = self.node_connections.get(node_id, [])
            dead: list[WebSocket] = []
            for ws in connections:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                if ws in connections:
                    connections.remove(ws)
                if ws in self.active:
                    self.active.remove(ws)

    def record_message(self, message: ArgusMessage) -> None:
        if message.id in self._seen_ids:
            return
        self._seen_ids.add(message.id)
        self.message_history.append(message)


class GuiServerState:
    """Shared state between FastAPI endpoints and the orchestrator."""

    def __init__(self, orchestrator: ArgusOrchestrator) -> None:
        self.orchestrator = orchestrator
        self.manager = ConnectionManager()
        self._bus_callback: Callable[[ArgusMessage], Awaitable[None]] = self._on_bus_message
        self._meeting_engine: MeetingEngine | None = None

    @property
    def meeting_engine(self) -> MeetingEngine:
        if self._meeting_engine is None:
            self._meeting_engine = MeetingEngine(
                bus=self.orchestrator.bus,
                router=self.orchestrator.router,
                memory_store=self.orchestrator.memory_store,
                response_timeout=300.0,
            )
        return self._meeting_engine

    async def _on_bus_message(self, message: ArgusMessage) -> None:
        self.manager.record_message(message)
        await self.manager.broadcast(message.to_dict())

    def make_human_handler(self, node_id: str):
        """Return a handler that forwards a node's messages to its WebSocket connections."""

        async def handler(message: ArgusMessage) -> None:
            await self.manager.send_to_node(node_id, message.to_dict())

        return handler

    async def start(self) -> None:
        await self.orchestrator.bus.subscribe_global(self._bus_callback)

    async def stop(self) -> None:
        await self.orchestrator.bus.unsubscribe_global(self._bus_callback)


def make_app(orchestrator: ArgusOrchestrator) -> FastAPI:
    """Build a FastAPI application wired to an orchestrator."""
    state = GuiServerState(orchestrator)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await state.start()
        yield {"state": state}
        await state.stop()

    app = FastAPI(title="Argus GUI API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/tree")
    def get_tree() -> dict[str, Any]:
        return orchestrator.tree.to_dict()

    @app.post("/api/tree")
    async def post_tree(payload: dict[str, Any]) -> dict[str, Any]:
        tree = CollaborationTree.from_dict(payload)
        path = Path(orchestrator.config.argus.collaboration_tree).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        tree.save(path)
        orchestrator.tree = tree
        orchestrator.router.tree = tree
        for agent in orchestrator._agents.values():
            agent.tree = tree
        return {"ok": True, "path": str(path)}

    @app.get("/api/nodes")
    def get_nodes() -> list[dict[str, Any]]:
        return [node.model_dump(by_alias=True) for node in orchestrator.tree.nodes]

    @app.get("/api/status")
    def get_status() -> dict[str, Any]:
        return orchestrator.status()

    @app.get("/api/nodes/{node_id}/status")
    def get_node_status(node_id: str) -> dict[str, Any]:
        status = orchestrator.status()
        if node_id not in status:
            return {"error": "node not found"}
        return status[node_id]

    @app.post("/api/humans/{node_id}/online")
    async def human_online(node_id: str) -> dict[str, Any]:
        """Mark a human node as online; messages will be pushed via WebSocket."""
        node = orchestrator.tree.get_node(node_id)
        if node is None or node.type != "human":
            return {"error": "not a human node"}
        handler = state.make_human_handler(node_id)
        orchestrator.register_human_handler(node_id, handler)
        return {"ok": True, "node_id": node_id, "online": True}

    @app.post("/api/humans/{node_id}/offline")
    async def human_offline(node_id: str) -> dict[str, Any]:
        """Mark a human node as offline; messages will be stored in its inbox."""
        node = orchestrator.tree.get_node(node_id)
        if node is None or node.type != "human":
            return {"error": "not a human node"}
        orchestrator.unregister_human_handler(node_id)
        return {"ok": True, "node_id": node_id, "online": False}

    @app.get("/api/humans/{node_id}/inbox")
    async def get_human_inbox(node_id: str) -> list[dict[str, Any]]:
        """Return messages waiting for an offline human node."""
        node = orchestrator.tree.get_node(node_id)
        if node is None or node.type != "human":
            return []
        messages = await orchestrator.human_manager.get_inbox(node_id)
        return [msg.to_dict() for msg in messages]

    @app.delete("/api/humans/{node_id}/inbox")
    async def clear_human_inbox(node_id: str) -> dict[str, Any]:
        """Clear a human node's inbox."""
        node = orchestrator.tree.get_node(node_id)
        if node is None or node.type != "human":
            return {"error": "not a human node"}
        count = await orchestrator.human_manager.clear_inbox(node_id)
        return {"ok": True, "node_id": node_id, "cleared": count}

    @app.post("/api/messages")
    async def post_message(payload: MessagePayload) -> dict[str, Any]:
        targets = payload.to
        if targets:
            if len(targets) == 1:
                message = await orchestrator.bus.send_private_async(
                    payload.from_id, targets[0], payload.text
                )
            else:
                message = await orchestrator.bus.send_group_async(
                    payload.from_id, payload.text, to=targets
                )
        else:
            message = await orchestrator.bus.send_group_async(payload.from_id, payload.text)
        return message.to_dict()

    @app.get("/api/messages/{node_id}")
    def get_messages(node_id: str) -> list[dict[str, Any]]:
        return [
            msg.to_dict()
            for msg in state.manager.message_history
            if node_id in msg.to or msg.from_id == node_id
        ]

    @app.get("/api/meetings")
    def list_meetings() -> list[dict[str, Any]]:
        return [m.to_transcript() for m in state.meeting_engine.list_meetings()]

    @app.post("/api/meetings")
    async def post_meeting(payload: MeetingPayload) -> dict[str, Any]:
        meeting = await state.meeting_engine.start_meeting(
            organizer=payload.organizer,
            participants=payload.participants,
            topic=payload.topic,
        )
        return meeting.to_transcript()

    @app.get("/api/meetings/{meeting_id}")
    def get_meeting(meeting_id: str) -> dict[str, Any]:
        meeting = state.meeting_engine.get_meeting(meeting_id)
        if meeting is None:
            return {"error": "meeting not found"}
        return meeting.to_transcript()

    @app.post("/api/meetings/{meeting_id}/close")
    async def close_meeting(meeting_id: str) -> dict[str, Any]:
        meeting = await state.meeting_engine.close_meeting(meeting_id)
        return meeting.to_transcript()

    class MeetingCommandPayload(BaseModel):
        """Payload for a human takeover command during a meeting."""

        command: str
        payload: str | None = None

    @app.post("/api/meetings/{meeting_id}/command")
    async def command_meeting(
        meeting_id: str,
        body: MeetingCommandPayload,
    ) -> dict[str, Any]:
        """Allow a human to issue a takeover command to a running meeting."""
        meeting = await state.meeting_engine.command_meeting(
            meeting_id,
            body.command,
            body.payload,
        )
        return meeting.to_transcript()

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket, node_id: str | None = None):
        """WebSocket endpoint; optional ``node_id`` binds the connection to a human node."""
        if node_id:
            node = orchestrator.tree.get_node(node_id)
            if node is None or node.type != "human":
                await websocket.close(code=4001, reason="not a human node")
                return
        await state.manager.connect(websocket, node_id=node_id)
        if node_id:
            handler = state.make_human_handler(node_id)
            orchestrator.register_human_handler(node_id, handler)
        try:
            while True:
                data = await websocket.receive_text()
                # Heartbeat from a human client keeps presence alive.
                if node_id:
                    await orchestrator.human_manager.heartbeat(node_id)
                await state.manager.broadcast({"type": "pong", "data": data})
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            if node_id:
                orchestrator.unregister_human_handler(node_id)
            await state.manager.disconnect(websocket, node_id=node_id)

    return app


class GuiServer:
    """Wrapper around uvicorn that runs in the same asyncio loop."""

    def __init__(self, orchestrator: ArgusOrchestrator, host: str, port: int) -> None:
        self.app = make_app(orchestrator)
        self.host = host
        self.port = port
        self.config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
            loop="asyncio",
            log_level="info",
        )
        self.server = uvicorn.Server(self.config)
        self._task: asyncio.Task[Any] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self.server.serve())

    async def stop(self) -> None:
        self.server.should_exit = True
        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:
                pass


def start_gui_server(
    orchestrator: ArgusOrchestrator,
    host: str,
    port: int,
) -> GuiServer:
    """Create and return a GUI server bound to the orchestrator.

    The returned server is not started; callers should await ``server.start()``.
    """
    return GuiServer(orchestrator, host, port)
