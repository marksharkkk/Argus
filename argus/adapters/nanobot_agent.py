"""nanobot Agent adapter for Argus.

Wraps one ``nanobot.agent.loop.AgentLoop`` per agent node and injects the
Argus-specific ``argus_send_message`` tool together with a collaboration-tree
aware system prompt.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from nanobot.agent.hook import AgentHook, AgentHookContext
from nanobot.agent.loop import AgentLoop
from nanobot.agent.tools.base import Tool
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import GenerationSettings
from nanobot.session.manager import SessionManager

from argus.config.schema import ArgusConfig
from argus.core.bus import ArgusBus
from argus.core.tree import CollaborationTree, Node


def _make_provider(config: ArgusConfig, model: str | None = None) -> Any:
    """Build a nanobot LLM provider from an Argus configuration.

    Mirrors nanobot's public provider-resolution logic using only public APIs.
    """
    from nanobot.providers.registry import find_by_name

    defaults = config.agents.defaults
    model = model or defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)
    spec = find_by_name(provider_name) if provider_name else None
    backend = spec.backend if spec else "openai_compat"

    if backend == "azure_openai":
        if not p or not p.api_key or not p.api_base:
            raise ValueError("Azure OpenAI requires api_key and api_base in config.")
        from nanobot.providers.azure_openai_provider import AzureOpenAIProvider

        provider = AzureOpenAIProvider(
            api_key=p.api_key,
            api_base=p.api_base,
            default_model=model,
        )
    elif backend == "openai_codex":
        from nanobot.providers.openai_codex_provider import OpenAICodexProvider

        provider = OpenAICodexProvider(default_model=model)
    elif backend == "github_copilot":
        from nanobot.providers.github_copilot_provider import GitHubCopilotProvider

        provider = GitHubCopilotProvider(default_model=model)
    elif backend == "anthropic":
        from nanobot.providers.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider(
            api_key=p.api_key if p else None,
            api_base=config.get_api_base(model),
            default_model=model,
            extra_headers=p.extra_headers if p else None,
        )
    else:
        if not model.startswith("bedrock/"):
            needs_key = not (p and p.api_key)
            exempt = spec and (spec.is_oauth or spec.is_local or spec.is_direct)
            if needs_key and not exempt:
                raise ValueError(f"No API key configured for provider '{provider_name}'.")
        from nanobot.providers.openai_compat_provider import OpenAICompatProvider

        provider = OpenAICompatProvider(
            api_key=p.api_key if p else None,
            api_base=config.get_api_base(model),
            default_model=model,
            extra_headers=p.extra_headers if p else None,
            spec=spec,
        )

    provider.generation = GenerationSettings(
        temperature=defaults.temperature,
        max_tokens=defaults.max_tokens,
        reasoning_effort=defaults.reasoning_effort,
    )
    return provider


def _build_argus_system_prompt(node: Node, tree: CollaborationTree) -> str:
    """Build the Argus-specific system-prompt section for an agent node."""
    reachable_ids = tree.get_reachable_nodes(node.id)

    lines: list[str] = [
        "# Argus Agent Context",
        "",
        f"You are agent node `{node.id}` (`{node.label}`).",
    ]
    if node.agent_id:
        lines.append(f"Agent identity: `{node.agent_id}`.")
    if node.metadata:
        lines.append(
            f"Role metadata: {json.dumps(node.metadata, ensure_ascii=False)}"
        )
    lines.append("")

    if reachable_ids:
        lines.append("You may communicate only with the following reachable nodes:")
        for rid in reachable_ids:
            target = tree.get_node(rid)
            if target is not None:
                lines.append(
                    f"- `{rid}` ({target.label}, type={target.type})"
                )
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
        ]
    )
    return "\n".join(lines)


class ArgusSendMessageTool(Tool):
    """Tool that lets an agent send Argus messages to other collaboration nodes."""

    def __init__(self, node: Node, tree: CollaborationTree, bus: ArgusBus) -> None:
        self._node = node
        self._tree = tree
        self._bus = bus

    @property
    def name(self) -> str:
        return "argus_send_message"

    @property
    def description(self) -> str:
        reachable = self._tree.get_reachable_nodes(self._node.id)
        reachable_text = ", ".join(f"`{rid}`" for rid in reachable) if reachable else "(none)"
        return (
            "Send a message to one or more reachable Argus collaboration nodes. "
            f"Reachable nodes from {self._node.id}: {reachable_text}. "
            "`to` may be a single node ID string or a list of node IDs; set "
            "`is_group=true` when addressing multiple nodes. You may only message "
            "nodes listed as reachable."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "to": {
                    "anyOf": [
                        {
                            "type": "string",
                            "description": "A single target node ID.",
                        },
                        {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "A list of target node IDs for group messaging.",
                        },
                    ],
                    "description": "Target node ID or list of node IDs.",
                },
                "text": {
                    "type": "string",
                    "description": "The message content to send.",
                },
                "is_group": {
                    "type": "boolean",
                    "description": "Whether this is a group message. Defaults to false.",
                    "default": False,
                },
            },
            "required": ["to", "text"],
        }

    def cast_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return parameters as-is; normalization happens in execute."""
        return params

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """Custom validation is performed inside execute."""
        return []

    async def execute(
        self,
        to: str | list[str],
        text: str,
        is_group: bool = False,
        **kwargs: Any,
    ) -> str:
        if isinstance(to, str):
            targets = [to]
        elif isinstance(to, list):
            targets = list(to)
        else:
            return "Error: 'to' must be a string node ID or a list of node IDs."

        if not targets:
            return "Error: 'to' must contain at least one target node ID."
        if not all(isinstance(t, str) for t in targets):
            return "Error: all target node IDs must be strings."

        if not is_group and len(targets) > 1:
            return (
                "Error: private message requires a single target. "
                "Either pass one target or set is_group=true."
            )

        invalid = [rid for rid in targets if not self._tree.can_communicate(self._node.id, rid)]
        if invalid:
            return f"Error: cannot communicate with unreachable nodes: {', '.join(invalid)}"

        if is_group or len(targets) > 1:
            self._bus.send_group(from_id=self._node.id, text=text, to=targets)
        else:
            self._bus.send_private(from_id=self._node.id, to_id=targets[0], text=text)

        return f"Message sent to {', '.join(targets)}."


class _ArgusSystemPromptHook(AgentHook):
    """Prepends the Argus collaboration context to the existing system prompt."""

    def __init__(self, node: Node, tree: CollaborationTree) -> None:
        self._prompt = _build_argus_system_prompt(node, tree)

    async def before_iteration(self, context: AgentHookContext) -> None:
        if not context.messages:
            return
        first = context.messages[0]
        if first.get("role") == "system":
            original = first.get("content", "")
            first["content"] = f"{self._prompt}\n\n---\n\n{original}"


class _ArgusOutboundHook(AgentHook):
    """Forward the agent's final text response to the Argus bus as a fallback.

    nanobot agents are expected to use the ``argus_send_message`` tool, but some
    models occasionally emit a plain final response instead. This hook ensures the
    response is still delivered to the original sender so the conversation does
    not silently stall.
    """

    def __init__(self, node: Node, tree: CollaborationTree, bus: ArgusBus) -> None:
        self._node = node
        self._tree = tree
        self._bus = bus

    @staticmethod
    def _extract_sender(text: str) -> tuple[str | None, bool]:
        """Parse sender prefix added by MessageRouter.

        Returns ``(sender_id, is_group)``.

        nanobot's ``ContextBuilder`` prepends a runtime context block before
        the user message, so the prefix is not necessarily at the start of
        ``text``. We therefore search for the prefix anywhere in the message.
        """
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

    async def after_iteration(self, context: AgentHookContext) -> None:
        logger.debug(
            "ArgusOutboundHook for {}: final_content={!r:.60} tool_results={}",
            self._node.id,
            context.final_content,
            len(context.tool_results),
        )
        if not context.final_content:
            return

        # Skip if the agent already used the Argus messaging tool.
        for result in context.tool_results:
            if isinstance(result, str) and result.startswith("Message sent to"):
                logger.debug("ArgusOutboundHook for {}: tool already sent message", self._node.id)
                return

        # Find the most recent user message (the incoming Argus prompt).
        last_user_text = None
        for msg in reversed(context.messages):
            if msg.get("role") == "user":
                last_user_text = msg.get("content", "")
                break
        if not last_user_text:
            logger.debug("ArgusOutboundHook for {}: no user message found", self._node.id)
            return

        original_sender, is_group = self._extract_sender(last_user_text)
        if not original_sender:
            logger.debug("ArgusOutboundHook for {}: could not extract sender", self._node.id)
            return
        if not self._tree.can_communicate(self._node.id, original_sender):
            logger.debug("ArgusOutboundHook for {}: cannot communicate with {}", self._node.id, original_sender)
            return

        text = context.final_content
        if is_group:
            reachable = [
                rid for rid in self._tree.get_reachable_nodes(self._node.id)
                if rid != self._node.id
            ]
            targets = [original_sender] if original_sender in reachable else []
            if targets:
                logger.info(
                    "ArgusOutboundHook for {}: forwarding final response as group to {}",
                    self._node.id,
                    targets,
                )
                self._bus.send_group(self._node.id, text, to=targets)
        else:
            logger.info(
                "ArgusOutboundHook for {}: forwarding final response as private to {}",
                self._node.id,
                original_sender,
            )
            self._bus.send_private(self._node.id, original_sender, text)


class NanobotAgentNode:
    """Adapter that runs one Argus agent node on top of nanobot's AgentLoop."""

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

        defaults = config.agents.defaults
        model = node.model or defaults.model
        provider = _make_provider(config, model=model)

        self._nanobot_bus = MessageBus()
        self._session_manager = SessionManager(self.workspace)

        self._loop = AgentLoop(
            bus=self._nanobot_bus,
            provider=provider,
            workspace=self.workspace,
            model=model,
            max_iterations=defaults.max_tool_iterations,
            context_window_tokens=defaults.context_window_tokens,
            context_block_limit=defaults.context_block_limit,
            max_tool_result_chars=defaults.max_tool_result_chars,
            provider_retry_mode=defaults.provider_retry_mode,
            web_config=config.tools.web,
            exec_config=config.tools.exec,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            mcp_servers=config.tools.mcp_servers,
            timezone=defaults.timezone,
            session_manager=self._session_manager,
            hooks=[
                _ArgusSystemPromptHook(node, tree),
                _ArgusOutboundHook(node, tree, argus_bus),
            ],
        )

        # Inject the Argus-specific message tool alongside nanobot's built-ins.
        self._loop.tools.register(
            ArgusSendMessageTool(node=node, tree=tree, bus=argus_bus)
        )

        self._task: asyncio.Task[Any] | None = None
        self._drain_task: asyncio.Task[Any] | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the agent's processing loop as a background task."""
        async with self._lock:
            if self.is_running():
                return
            await self.argus_bus.register_node(self.node.id)
            self._task = asyncio.create_task(self._loop.run())
            self._drain_task = asyncio.create_task(self._drain_outbound())

    async def stop(self) -> None:
        """Stop the agent loop gracefully and drain background work."""
        async with self._lock:
            if not self.is_running():
                return

            self._loop.stop()
            task = self._task
            drain_task = self._drain_task
            self._task = None
            self._drain_task = None

            if task is not None:
                try:
                    await asyncio.wait_for(task, timeout=5.0)
                except asyncio.TimeoutError:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                except asyncio.CancelledError:
                    pass

            if drain_task is not None:
                drain_task.cancel()
                try:
                    await drain_task
                except asyncio.CancelledError:
                    pass

            await self._loop.close_mcp()

    async def _drain_outbound(self) -> None:
        """Drain nanobot's outbound queue so it does not grow unbounded.

        The Argus adapter delivers responses through hooks rather than by
        consuming from nanobot's outbound queue. Progress messages, error
        replies and stream fragments are still published to that queue by
        nanobot's AgentLoop, so we continuously pull and drop them here.
        """
        while True:
            try:
                msg = await self._nanobot_bus.consume_outbound()
            except asyncio.CancelledError:
                # Drain any remaining items before exiting so shutdown is clean.
                while self._nanobot_bus.outbound_size > 0:
                    try:
                        self._nanobot_bus.outbound.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                raise
            except Exception:
                logger.exception("Error draining outbound queue for %s", self.node.id)
                await asyncio.sleep(0.1)
                continue
            logger.debug(
                "Drained outbound message for %s: %r",
                self.node.id,
                msg.content[:80] if msg.content else "",
            )

    async def send_to_agent(self, text: str) -> None:
        """Inject a user message into the agent's inbound queue."""
        message = InboundMessage(
            channel="argus",
            sender_id="user",
            chat_id=self.node.id,
            content=text,
            metadata={"argus_node_id": self.node.id},
        )
        await self._nanobot_bus.publish_inbound(message)

    def is_running(self) -> bool:
        """Return True if the background processing task is active."""
        return self._task is not None and not self._task.done()

    def status(self) -> dict[str, Any]:
        """Return a snapshot of the node's runtime status."""
        return {
            "node_id": self.node.id,
            "label": self.node.label,
            "running": self.is_running(),
            "inbound_queue_size": self._nanobot_bus.inbound_size,
            "outbound_queue_size": self._nanobot_bus.outbound_size,
            "workspace": str(self.workspace),
            "session_count": len(self._session_manager.list_sessions()),
            "tools": self._loop.tools.tool_names,
        }
