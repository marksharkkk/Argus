"""Argus meeting engine."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Literal

from argus.core.bus import ArgusBus
from argus.core.message import ArgusMessage, make_group_message
from argus.core.router import MessageRouter

logger = logging.getLogger(__name__)


MeetingStatus = Literal["pending", "running", "closed"]


class Meeting:
    """A meeting session with participants and message history."""

    def __init__(
        self,
        topic: str,
        organizer: str,
        participants: list[str],
        meeting_id: str | None = None,
    ) -> None:
        self.id: str = meeting_id or str(uuid.uuid4())
        self.topic: str = topic
        self.organizer: str = organizer
        self.participants: list[str] = list(participants)
        self.history: list[ArgusMessage] = []
        self.status: MeetingStatus = "pending"
        self.created_at: datetime = datetime.now(timezone.utc)
        self.closed_at: datetime | None = None
        self.command_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self.interrupted: bool = False
        self.current_turn: str | None = None

    def add_message(self, message: ArgusMessage) -> None:
        """Append a message to the meeting history."""
        self.history.append(message)

    def set_command(self, command: str, payload: Any | None = None) -> None:
        """Enqueue a human takeover command for the running meeting."""
        self.command_queue.put_nowait((command, payload))

    def is_active(self) -> bool:
        """Return True if the meeting is still running."""
        return self.status == "running"

    def to_transcript(self) -> dict[str, Any]:
        """Serialize the meeting to a memory-store compatible transcript dict."""
        messages = [
            {
                "speaker": msg.from_id,
                "text": msg.text,
                "timestamp": msg.timestamp.isoformat(),
            }
            for msg in self.history
        ]

        return {
            "id": self.id,
            "topic": self.topic,
            "organizer": self.organizer,
            "participants": self.participants,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "messages": messages,
        }


ResponseProvider = Callable[[str, str, list[ArgusMessage]], Awaitable[str]]


class BusResponseProvider:
    """Capture outbound messages from meeting participants via the ArgusBus.

    The provider subscribes to the monitored nodes and collects messages whose
    ``from_id`` is one of the monitored participants. This allows the meeting
    engine to wait for a participant's reply after sending a turn prompt.
    """

    def __init__(self, bus: ArgusBus, nodes_to_monitor: list[str]) -> None:
        self.bus = bus
        self._monitored = set(nodes_to_monitor)
        self._queues: dict[str, asyncio.Queue[str]] = {}
        self._callback: Callable[[ArgusMessage], Awaitable[None]] | None = None

    async def start(self) -> None:
        """Subscribe to monitored nodes to collect their outbound messages."""
        self._callback = self._on_message
        for node_id in self._monitored:
            self._queues[node_id] = asyncio.Queue()
            await self.bus.subscribe(node_id, self._callback)

    async def stop(self) -> None:
        """Unsubscribe from monitored nodes."""
        if self._callback is None:
            return
        for node_id in self._monitored:
            await self.bus.unsubscribe(node_id, self._callback)
        self._callback = None
        self._queues.clear()

    async def _on_message(self, message: ArgusMessage) -> None:
        """Store messages sent by monitored nodes."""
        if message.from_id in self._monitored:
            queue = self._queues.get(message.from_id)
            if queue is not None:
                await queue.put(message.text)

    async def get_response(self, participant_id: str, timeout: float | None = None) -> str:
        """Wait for the next outbound message from ``participant_id``."""
        queue = self._queues.get(participant_id)
        if queue is None:
            raise ValueError(f"Participant {participant_id} is not monitored")
        timeout = timeout if timeout is not None else 60.0
        return await asyncio.wait_for(queue.get(), timeout=timeout)


class MeetingEngine:
    """Orchestrate Argus meetings over a collaboration tree."""

    def __init__(
        self,
        bus: ArgusBus,
        router: MessageRouter,
        memory_store: Any | None = None,
        response_provider: ResponseProvider | None = None,
        response_timeout: float = 60.0,
    ) -> None:
        self.bus = bus
        self.router = router
        self.memory_store = memory_store
        self.response_provider = response_provider
        self.response_timeout = response_timeout
        self._meetings: dict[str, Meeting] = {}
        self._active_providers: dict[str, BusResponseProvider] = {}
        self._meeting_tasks: dict[str, asyncio.Task[Any]] = {}

    async def start_meeting(
        self,
        organizer: str,
        participants: list[str],
        topic: str,
    ) -> Meeting:
        """Start a new meeting and return immediately.

        The actual round-robin and free-discussion phases run in a background
        task so that humans can issue takeover commands while the meeting is in
        progress.

        Args:
            organizer: Node ID of the meeting organizer.
            participants: Node IDs attending the meeting.
            topic: Meeting topic.

        Returns:
            The running ``Meeting`` instance.
        """
        self._validate_node(organizer)
        for pid in participants:
            self._validate_node(pid)

        meeting = Meeting(topic=topic, organizer=organizer, participants=participants)
        self._meetings[meeting.id] = meeting
        meeting.status = "running"

        task = asyncio.create_task(self._run_meeting(meeting))
        self._meeting_tasks[meeting.id] = task

        return meeting

    async def close_meeting(self, meeting_id: str) -> Meeting:
        """Close a meeting and archive its transcript.

        Args:
            meeting_id: ID of the meeting to close.

        Returns:
            The closed ``Meeting`` instance.
        """
        meeting = self._meetings.get(meeting_id)
        if meeting is None:
            raise ValueError(f"Meeting not found: {meeting_id}")

        meeting.status = "closed"
        meeting.closed_at = datetime.now(timezone.utc)

        close_msg = await self._broadcast(
            meeting,
            meeting.organizer,
            "会议结束。",
            metadata={"kind": "meeting_close"},
        )
        meeting.add_message(close_msg)

        provider = self._active_providers.pop(meeting_id, None)
        if provider is not None:
            await provider.stop()

        if self.memory_store is not None:
            self.memory_store.save_meeting(None, meeting.to_transcript())

        task = self._meeting_tasks.pop(meeting_id, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        return meeting

    async def command_meeting(
        self,
        meeting_id: str,
        command: str,
        payload: Any | None = None,
    ) -> Meeting:
        """Issue a human takeover command to a running meeting.

        Supported commands:
        - ``close``: immediately close the meeting.
        - ``update_topic``: change the topic to ``payload`` and broadcast it.
        - ``skip_turn``: skip the current agent's turn.
        """
        meeting = self._meetings.get(meeting_id)
        if meeting is None:
            raise ValueError(f"Meeting not found: {meeting_id}")
        if meeting.status != "running":
            raise ValueError(f"Meeting {meeting_id} is not running")

        meeting.set_command(command, payload)
        return meeting

    async def _run_meeting(self, meeting: Meeting) -> None:
        """Run the meeting lifecycle in a background task."""
        try:
            participants = meeting.participants
            organizer = meeting.organizer

            start_msg = await self._broadcast(
                meeting,
                organizer,
                f"会议开始：{meeting.topic}",
                metadata={"kind": "meeting_start"},
            )
            meeting.add_message(start_msg)

            agent_participants = [
                pid for pid in participants if self._get_node_type(pid) == "agent"
            ]

            provider: BusResponseProvider | None = None
            if self.response_provider is None:
                provider = BusResponseProvider(
                    self.bus, list(participants) + [organizer]
                )
                await provider.start()
                self._active_providers[meeting.id] = provider

            for participant in agent_participants:
                if not meeting.is_active():
                    break

                prompt = self._build_turn_prompt(meeting, participant)
                response = await self._run_turn(
                    meeting, participant, prompt, provider
                )
                if response is None:
                    # Turn was skipped or meeting was closed by a human command.
                    continue

                broadcast_msg = await self._broadcast(
                    meeting,
                    participant,
                    response,
                    metadata={"kind": "turn_response"},
                )
                meeting.add_message(broadcast_msg)

            if meeting.is_active():
                free_msg = await self._broadcast(
                    meeting,
                    organizer,
                    "现在进入自由讨论阶段，参与者可以互相 @。",
                    metadata={"kind": "free_discussion"},
                )
                meeting.add_message(free_msg)
                # During free discussion the meeting stays running until a human
                # explicitly closes it. We wait for the close command here so
                # that ``command_meeting(close)`` ends this task cleanly.
                await self._wait_for_close_command(meeting)

        except asyncio.CancelledError:
            # Allow the meeting to be cancelled when the orchestrator shuts down.
            raise
        except Exception:
            logger.exception("Meeting %s runner encountered an error", meeting.id)
        finally:
            provider = self._active_providers.pop(meeting.id, None)
            if provider is not None:
                await provider.stop()
            self._meeting_tasks.pop(meeting.id, None)
            if meeting.is_active():
                meeting.status = "closed"
                meeting.closed_at = datetime.now(timezone.utc)

    async def _run_turn(
        self,
        meeting: Meeting,
        participant_id: str,
        prompt: str,
        provider: BusResponseProvider | None,
    ) -> str | None:
        """Run a single agent turn, allowing human commands to interrupt it."""
        meeting.current_turn = participant_id

        if self.response_provider is not None:
            response_task: asyncio.Task[str] = asyncio.create_task(
                self.response_provider(participant_id, prompt, list(meeting.history))
            )
        else:
            assert provider is not None
            self.bus.send_private(
                meeting.organizer,
                participant_id,
                prompt,
                metadata={"meeting_id": meeting.id, "kind": "turn_prompt"},
            )
            response_task = asyncio.create_task(
                provider.get_response(participant_id, self.response_timeout)
            )

        command_task = asyncio.create_task(meeting.command_queue.get())
        done, pending = await asyncio.wait(
            [response_task, command_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if command_task in done:
            command, payload = command_task.result()
            result = await self._handle_command(meeting, command, payload)
            meeting.current_turn = None
            return result

        meeting.current_turn = None
        return response_task.result()

    async def _handle_command(
        self,
        meeting: Meeting,
        command: str,
        payload: Any | None,
    ) -> str | None:
        """Apply a human takeover command and return a response if any."""
        if command == "close":
            await self.close_meeting(meeting.id)
            return None

        if command == "skip_turn":
            skip_msg = await self._broadcast(
                meeting,
                meeting.organizer,
                f"主持人跳过 {meeting.current_turn or '当前'} 的发言。",
                metadata={"kind": "turn_skipped"},
            )
            meeting.add_message(skip_msg)
            return None

        if command == "update_topic":
            new_topic = str(payload) if payload else meeting.topic
            meeting.topic = new_topic
            topic_msg = await self._broadcast(
                meeting,
                meeting.organizer,
                f"主持人将会议议题更新为：{new_topic}",
                metadata={"kind": "topic_updated"},
            )
            meeting.add_message(topic_msg)
            return None

        # Unknown commands are ignored.
        return None

    async def _wait_for_close_command(self, meeting: Meeting) -> None:
        """Block until the meeting is closed by a human command."""
        while meeting.is_active():
            try:
                command, payload = await meeting.command_queue.get()
            except asyncio.CancelledError:
                raise
            await self._handle_command(meeting, command, payload)

    async def wait_for_meeting(self, meeting_id: str) -> Meeting:
        """Wait for a meeting's background task to finish.

        The task finishes when the meeting is closed, either by a human command
        or by ``close_meeting``.
        """
        task = self._meeting_tasks.get(meeting_id)
        if task is not None and not task.done():
            await task
        return self._meetings[meeting_id]

    def get_meeting(self, meeting_id: str) -> Meeting | None:
        """Return a meeting by ID."""
        return self._meetings.get(meeting_id)

    def list_meetings(self) -> list[Meeting]:
        """Return all meetings, most recent first."""
        return sorted(
            self._meetings.values(),
            key=lambda m: m.created_at,
            reverse=True,
        )

    def _validate_node(self, node_id: str) -> None:
        if self.router.tree.get_node(node_id) is None:
            raise ValueError(f"Unknown node: {node_id}")

    def _get_node_type(self, node_id: str) -> str | None:
        node = self.router.tree.get_node(node_id)
        return node.type if node is not None else None

    def _build_turn_prompt(self, meeting: Meeting, participant_id: str) -> str:
        history_text = self._format_history(meeting.history)
        return (
            f"这是关于「{meeting.topic}」的会议。\n\n"
            f"当前会议历史：\n{history_text}\n\n"
            f"现在轮到 {participant_id} 发言，请发表你的观点。"
        )

    async def _broadcast(
        self,
        meeting: Meeting,
        sender_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> ArgusMessage:
        """Dispatch a group message to all meeting participants.

        Unlike ``bus.send_group``, this bypasses the collaboration-tree
        reachability filter so the organizer (usually a human node) always
        receives system messages such as meeting start and topic updates.
        """
        message = make_group_message(
            sender_id,
            text,
            to=list(meeting.participants),
            metadata={**(metadata or {}), "meeting_id": meeting.id},
        )
        await self.bus.dispatch(message)
        return message

    @staticmethod
    def _format_history(history: list[ArgusMessage]) -> str:
        if not history:
            return "（暂无）"
        lines = []
        for msg in history:
            prefix = "[群聊]" if msg.is_group else "[私聊]"
            targets = ", ".join(msg.to) if msg.to else "all"
            lines.append(f"{prefix} {msg.from_id} -> {targets}: {msg.text}")
        return "\n".join(lines)
