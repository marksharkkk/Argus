"""Real LLM agent adapter for Argus.

Uses an OpenAI-compatible HTTP API (DeepSeek, OpenAI, Azure OpenAI, etc.) to
drive agent nodes.  Agents receive messages from the Argus bus, call the LLM
with a collaboration-tree-aware system prompt and an ``argus_send_message``
tool, then route their replies back through the bus.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from argus.config.schema import ArgusConfig
from argus.core.bus import ArgusBus
from argus.core.message import ArgusMessage
from argus.core.tree import CollaborationTree, Node

logger = logging.getLogger(__name__)


def _build_system_prompt(node: Node, tree: CollaborationTree) -> str:
    """Build the collaboration-tree-aware system prompt for an agent."""
    reachable_ids = tree.get_reachable_nodes(node.id)
    lines: list[str] = [
        "# Argus Agent Context",
        "",
        f"You are agent node `{node.id}` (`{node.label}`).",
    ]
    if node.agent_id:
        lines.append(f"Agent identity: `{node.agent_id}`.")
    if node.metadata:
        lines.append(f"Role metadata: {json.dumps(node.metadata, ensure_ascii=False)}")
    lines.append("")

    if reachable_ids:
        lines.append("You may communicate only with the following reachable nodes:")
        for rid in reachable_ids:
            target = tree.get_node(rid)
            if target is not None:
                lines.append(f"- `{rid}` ({target.label}, type={target.type})")
            else:
                lines.append(f"- `{rid}`")
    else:
        lines.append("You have no reachable nodes in the collaboration tree.")

    lines.extend(
        [
            "",
            "Use the `argus_send_message` tool to send messages to other nodes.",
            "Parameters:",
            "- `to`: list of target node IDs (use a single-element list for a private message)",
            "- `text`: the message content",
            "- `is_group`: set to `true` for a group message; omit or `false` for a private message",
            "",
            "You must only target reachable nodes. Do not attempt to communicate with unreachable nodes.",
            "When replying to a message, prefer targeting the original sender or the group it came from.",
        ]
    )
    return "\n".join(lines)


class LLMAgentNode:
    """Agent node backed by a real LLM through an OpenAI-compatible API."""

    def __init__(
        self,
        node: Node,
        tree: CollaborationTree,
        argus_bus: ArgusBus,
        config: ArgusConfig,
        workspace: Path | None = None,
    ) -> None:
        self.node = node
        self.tree = tree
        self.argus_bus = argus_bus
        self.config = config

        base_workspace = workspace or config.workspace_path
        self.workspace = base_workspace / "argus" / "nodes" / node.id
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.model = node.model or config.agents.defaults.model
        self.provider_name = config.get_provider_name(self.model)
        self.provider = config.get_provider(self.model)

        self._client: Any | None = None
        self._running = False
        self._task: asyncio.Task[Any] | None = None
        self._inbox: asyncio.Queue[ArgusMessage] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._session_count = 0
        self._messages_received = 0
        self._history: list[dict[str, Any]] = [
            {"role": "system", "content": _build_system_prompt(node, tree)},
        ]

    @property
    def _api_model_name(self) -> str:
        """Return the model name as expected by the LLM API endpoint."""
        # Config uses "provider/model" convention; APIs only need the model part.
        if "/" in self.model:
            provider, _, model_name = self.model.partition("/")
            if provider == self.provider_name:
                return model_name
        return self.model

    def _ensure_client(self) -> Any:
        """Lazy-build an OpenAI-compatible async client."""
        if self._client is not None:
            return self._client

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The 'openai' package is required for real LLM mode. "
                "Install it with: pip install openai"
            ) from exc

        if not self.provider:
            raise ValueError(
                f"No provider configured for model '{self.model}'. "
                "Add a providers entry to your Argus config."
            )

        api_key = self.provider.api_key
        api_base = self.provider.api_base
        if not api_key:
            raise ValueError(
                f"Provider '{self.provider_name}' has no api_key configured."
            )

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=api_base,
            default_headers=self.provider.extra_headers or {},
        )
        return self._client

    async def start(self) -> None:
        async with self._lock:
            if self._running:
                return
            await self.argus_bus.register_node(self.node.id)
            self._running = True
            self._task = asyncio.create_task(self._loop())
            logger.info("LLM agent %s started (model=%s)", self.node.id, self.model)

    async def stop(self) -> None:
        async with self._lock:
            if not self._running:
                return
            self._running = False
            task = self._task
            self._task = None
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            logger.info("LLM agent %s stopped", self.node.id)

    async def send_to_agent(self, text: str) -> None:
        """Inject a message into the agent's inbox."""
        message = ArgusMessage(
            from_id="user",
            to=[self.node.id],
            text=text,
        )
        await self._inbox.put(message)

    def is_running(self) -> bool:
        return self._running

    def status(self) -> dict[str, Any]:
        return {
            "node_id": self.node.id,
            "label": self.node.label,
            "running": self.is_running(),
            "model": self.model,
            "provider": self.provider_name,
            "workspace": str(self.workspace),
            "session_count": self._session_count,
            "messages_received": self._messages_received,
            "tools": ["argus_send_message"],
        }

    async def _loop(self) -> None:
        """Process incoming messages and ask the LLM for replies."""
        while self._running:
            try:
                message = await asyncio.wait_for(self._inbox.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            self._messages_received += 1
            logger.debug("LLM agent %s received: %s", self.node.id, message.text)

            try:
                await self._process_message(message)
            except Exception:
                logger.exception("LLM agent %s failed to process message", self.node.id)

    def _extract_sender_info(self, text: str) -> tuple[str | None, bool]:
        """Parse the sender prefix added by MessageRouter."""
        for prefix, is_group, offset in (
            ("[group from:", True, 12),
            ("[from:", False, 6),
        ):
            idx = text.find(prefix)
            if idx != -1:
                end = text.find("]", idx)
                if end != -1:
                    return text[idx + offset:end].strip(), is_group
        return None, False

    async def _process_message(self, message: ArgusMessage) -> None:
        """Send the message to the LLM and act on the response."""
        raw_text = message.text
        original_sender, is_group = self._extract_sender_info(raw_text)
        if original_sender is None:
            original_sender = message.from_id

        # Strip the internal routing prefix before showing it to the LLM.
        clean_text = raw_text
        for prefix in ("[group from:", "[from:"):
            idx = clean_text.find(prefix)
            if idx != -1:
                end = clean_text.find("]", idx)
                if end != -1:
                    clean_text = clean_text[end + 1 :].strip()
                break

        group_note = " (group message)" if is_group else ""
        user_content = f"[from: {original_sender}{group_note}] {clean_text}"

        self._history.append({"role": "user", "content": user_content})

        tool_response = await self._call_llm_with_tool(original_sender, is_group)
        if tool_response is False:
            # LLM returned content without using the tool. The content has already
            # been appended to history; retrieve it and send as a plain reply.
            fallback = self._history[-1].get("content") if self._history else None
            if fallback:
                await self._send_reply(original_sender, is_group, fallback)
        elif tool_response is None:
            # LLM call failed: try a plain completion as a last resort.
            fallback = await self._call_llm_plain()
            if fallback:
                await self._send_reply(original_sender, is_group, fallback)

    async def _call_llm_with_tool(
        self,
        original_sender: str,
        is_group: bool,
    ) -> bool | None:
        """Call the LLM with the argus_send_message tool.

        Returns ``True`` if a tool call was handled, ``False`` if no tool call
        was made, or ``None`` on error.
        """
        client = self._ensure_client()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "argus_send_message",
                    "description": (
                        "Send a message to one or more reachable Argus collaboration nodes. "
                        "Use a single target for private messages and multiple targets (or the original group) "
                        "for group messages."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of target node IDs.",
                            },
                            "text": {
                                "type": "string",
                                "description": "The message content to send.",
                            },
                            "is_group": {
                                "type": "boolean",
                                "description": "Whether this is a group message.",
                                "default": False,
                            },
                        },
                        "required": ["to", "text"],
                    },
                },
            }
        ]

        try:
            response = await client.chat.completions.create(
                model=self._api_model_name,
                messages=self._history,
                tools=tools,
                tool_choice="auto",
                temperature=self.config.agents.defaults.temperature,
                max_tokens=self.config.agents.defaults.max_tokens,
            )
        except Exception:
            logger.exception("LLM call failed for %s", self.node.id)
            return None

        choice = response.choices[0]
        message = choice.message

        # Record the assistant's response in history.
        assistant_msg: dict[str, Any] = {"role": "assistant"}
        if message.content:
            assistant_msg["content"] = message.content
        if message.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]
        self._history.append(assistant_msg)

        if not message.tool_calls:
            return False

        for tool_call in message.tool_calls:
            if tool_call.function.name != "argus_send_message":
                logger.warning(
                    "Agent %s called unknown tool %s",
                    self.node.id,
                    tool_call.function.name,
                )
                continue

            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                logger.warning(
                    "Agent %s passed invalid JSON tool arguments: %s",
                    self.node.id,
                    tool_call.function.arguments,
                )
                continue

            await self._handle_send_message_tool(args, original_sender, is_group)

        return True

    async def _call_llm_plain(self) -> str | None:
        """Fallback plain completion without tools."""
        client = self._ensure_client()
        try:
            response = await client.chat.completions.create(
                model=self._api_model_name,
                messages=self._history,
                temperature=self.config.agents.defaults.temperature,
                max_tokens=self.config.agents.defaults.max_tokens,
            )
        except Exception:
            logger.exception("LLM fallback call failed for %s", self.node.id)
            return None

        content = response.choices[0].message.content
        if content:
            self._history.append({"role": "assistant", "content": content})
        return content

    async def _handle_send_message_tool(
        self,
        args: dict[str, Any],
        original_sender: str,
        is_group: bool,
    ) -> None:
        """Execute the argus_send_message tool."""
        to_raw = args.get("to", [])
        text = args.get("text", "")
        is_group_arg = args.get("is_group", False)

        if isinstance(to_raw, str):
            targets = [to_raw]
        elif isinstance(to_raw, list):
            targets = [str(t) for t in to_raw]
        else:
            targets = []

        if not targets or not text:
            logger.warning("Agent %s sent empty tool args: %s", self.node.id, args)
            return

        # Validate reachability.
        invalid = [t for t in targets if not self.tree.can_communicate(self.node.id, t)]
        if invalid:
            logger.warning(
                "Agent %s tried to message unreachable nodes: %s",
                self.node.id,
                invalid,
            )
            targets = [t for t in targets if t not in invalid]
            if not targets:
                return

        if is_group_arg or len(targets) > 1:
            self.argus_bus.send_group(
                from_id=self.node.id,
                text=text,
                to=targets,
            )
        else:
            self.argus_bus.send_private(
                from_id=self.node.id,
                to_id=targets[0],
                text=text,
            )

    async def _send_reply(
        self,
        original_sender: str,
        is_group: bool,
        text: str,
    ) -> None:
        """Send a fallback text reply back to the original sender/group."""
        if is_group:
            reachable = set(self.tree.get_reachable_nodes(self.node.id))
            reachable.discard(self.node.id)
            if original_sender in reachable:
                self.argus_bus.send_group(
                    from_id=self.node.id,
                    text=text,
                    to=sorted(reachable),
                )
        else:
            if self.tree.can_communicate(self.node.id, original_sender):
                self.argus_bus.send_private(
                    from_id=self.node.id,
                    to_id=original_sender,
                    text=text,
                )
