"""Argus CLI entry point."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.rule import Rule
from rich.table import Table

from argus.config.loader import get_argus_config_path, load_argus_config, save_argus_config
from argus.config.schema import ArgusConfig
from argus.core.message import ArgusMessage
from argus.core.orchestrator import ArgusOrchestrator
from argus.core.tree import CollaborationTree, parse_mentions
from argus.i18n import t
from argus.memory.store import MemoryStore

app = typer.Typer(
    name="argus",
    help="Argus - Multi-Agent Collaboration Orchestration Platform",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console(legacy_windows=True)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_TREE_PATH = PROJECT_ROOT / "config" / "example_tree.yaml"


def _success(message: str) -> None:
    console.print(f"[bold green][OK][/bold green] {message}")


def _info(message: str) -> None:
    console.print(f"[dim]{message}[/dim]")


def _error(message: str) -> None:
    console.print(f"[bold red][ERR][/bold red] {message}")


def _expand_path(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _load_config_and_tree() -> tuple[ArgusConfig, CollaborationTree]:
    """Load Argus configuration and collaboration tree."""
    config_path = get_argus_config_path()
    config = load_argus_config(config_path)

    tree_path = _expand_path(config.argus.collaboration_tree)
    if not tree_path.exists():
        _error(f"Collaboration tree not found: {tree_path}")
        raise typer.Exit(code=1)

    tree = CollaborationTree.from_file(tree_path)
    return config, tree


def _ensure_memory_store(config: ArgusConfig) -> MemoryStore:
    return MemoryStore(_expand_path(config.argus.memory_dir))


def _write_pid_file(pid_path: Path) -> None:
    pid_path.write_text(str(os.getpid()), encoding="utf-8")


def _remove_pid_file(pid_path: Path) -> None:
    try:
        pid_path.unlink(missing_ok=True)
    except OSError:
        pass


def _read_pid_file(pid_path: Path) -> int | None:
    try:
        return int(pid_path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _is_heartbeat_fresh(status_path: Path, threshold_seconds: float = 30.0) -> bool:
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
        timestamp = datetime.fromisoformat(data.get("timestamp", "1970-01-01T00:00:00+00:00"))
        elapsed = (datetime.now(timezone.utc) - timestamp).total_seconds()
        return elapsed < threshold_seconds
    except (ValueError, OSError):
        return False


@app.command()
def onboard() -> None:
    """Initialize the Argus workspace in your home directory."""
    argus_dir = Path.home() / ".argus"
    memory_dir = argus_dir / "memory"

    argus_dir.mkdir(parents=True, exist_ok=True)
    memory_dir.mkdir(parents=True, exist_ok=True)

    for layer in ("projects", "team", "agents", "meetings", "modes"):
        (memory_dir / layer).mkdir(parents=True, exist_ok=True)

    config_path = argus_dir / "config.json"
    config: ArgusConfig | None = None
    if not config_path.exists():
        config = ArgusConfig()
        save_argus_config(config, config_path)
        _success(f"{t('workspace_initialized')}: {config_path}")
    else:
        config = load_argus_config(config_path)
        _info(f"Configuration already exists: {config_path}")

    tree_path = argus_dir / "collaboration_tree.yaml"
    if not tree_path.exists():
        if EXAMPLE_TREE_PATH.exists():
            shutil.copy2(EXAMPLE_TREE_PATH, tree_path)
            _success(f"Copied example collaboration tree: {tree_path}")
        else:
            _error(f"Example tree not found at {EXAMPLE_TREE_PATH}; skipping copy")
    else:
        _info(f"Collaboration tree already exists: {tree_path}")

    for name in ("best_practices.md", "lessons_learned.md"):
        path = memory_dir / "team" / name
        if not path.exists():
            path.write_text(f"# {name.replace('_', ' ').title()}\n\n", encoding="utf-8")
            _success(f"Created team memory file: {path}")
        else:
            _info(f"Team memory file already exists: {path}")

    ready_text = t("onboard_done", config)
    console.print(f"[bold green]{ready_text}[/bold green]")
    console.print("")
    console.print(f"Home: [cyan]{argus_dir}[/cyan]")
    console.print(f"Config: [cyan]{config_path}[/cyan]")
    console.print(f"Tree: [cyan]{tree_path}[/cyan]")


@app.command()
def gateway(
    mock: Annotated[
        bool,
        typer.Option("--mock", help="Use mock agents instead of real LLM agents"),
    ] = False,
) -> None:
    """Start the Argus gateway orchestrator."""
    config, tree = _load_config_and_tree()
    memory_store = _ensure_memory_store(config)
    status_dir = _expand_path(config.argus.memory_dir).parent
    pid_path = status_dir / "gateway.pid"

    if mock:
        _info("Mock mode enabled: agents will use deterministic replies")

    orchestrator = ArgusOrchestrator(
        config=config,
        tree=tree,
        memory_store=memory_store,
        status_dir=status_dir,
        mock=mock,
    )

    async def _run() -> None:
        _write_pid_file(pid_path)
        try:
            start_text = t("gateway_started", config)
            console.print(
                f"[bold green]{start_text}[/bold green] with {len(tree.nodes)} tree nodes"
            )
            await orchestrator.run()
        finally:
            _remove_pid_file(pid_path)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print(f"\n[yellow]{t('cancelled', config)}[/yellow]")
    finally:
        _remove_pid_file(pid_path)

    console.print(f"[bold green]{t('gateway_stopped', config)}[/bold green]")


@app.command()
def agent(
    node: Annotated[str, typer.Option("--node", help="Human node ID to operate as")],
    message: Annotated[
        str | None,
        typer.Option("-m", "--message", help="Initial message to send after startup"),
    ] = None,
    mock: Annotated[
        bool,
        typer.Option("--mock", help="Use mock agents instead of real LLM agents"),
    ] = False,
) -> None:
    """Run an interactive human agent in the terminal."""
    config, tree = _load_config_and_tree()

    human_node = tree.get_node(node)
    if human_node is None:
        _error(f"Unknown human node: {node}")
        raise typer.Exit(code=1)
    if human_node.type != "human":
        _error(f"Node {node} is not a human node")
        raise typer.Exit(code=1)

    if mock:
        _info("Mock mode enabled: agents will use deterministic replies")

    memory_store = _ensure_memory_store(config)
    orchestrator = ArgusOrchestrator(
        config=config,
        tree=tree,
        memory_store=memory_store,
        mock=mock,
    )

    print_lock = asyncio.Lock()

    async def human_handler(message: ArgusMessage) -> None:
        async with print_lock:
            sender = message.from_id
            targets = ", ".join(message.to) if message.to else "all"
            prefix = "[群聊]" if message.is_group else "[私聊]"
            console.print(
                f"\n[bold cyan]{prefix} {sender} → {targets}:[/bold cyan] {message.text}"
            )
            console.print("[dim]you> [/dim]", end="")

    orchestrator.register_human_handler(node, human_handler)

    async def input_loop() -> None:
        while orchestrator.is_running:
            try:
                async with print_lock:
                    console.print("[dim]you> [/dim]", end="")
                line = await asyncio.to_thread(input)
            except EOFError:
                orchestrator.request_shutdown()
                break

            text = line.strip()
            if not text:
                continue
            if text.lower() in ("/quit", "/exit", "/q"):
                orchestrator.request_shutdown()
                break

            mentions = parse_mentions(text)
            if mentions:
                targets = [m for m in mentions if m != "all"]
                if not targets or "all" in mentions:
                    orchestrator.bus.send_group(node, text)
                elif len(targets) == 1:
                    orchestrator.bus.send_private(node, targets[0], text)
                else:
                    orchestrator.bus.send_group(node, text, to=targets)
            else:
                orchestrator.bus.send_group(node, text)

    async def _run() -> None:
        await orchestrator.start()
        joined_text = t("agent_joined", config)
        console.print(
            f"[bold green]{joined_text} '{node}'[/bold green] "
            f"({human_node.label}). Type /quit or press Ctrl+C to exit."
        )
        if message:
            orchestrator.bus.send_group(node, message)
        input_task = asyncio.create_task(input_loop())
        try:
            if orchestrator.shutdown_event is not None:
                await orchestrator.shutdown_event.wait()
        finally:
            input_task.cancel()
            try:
                await input_task
            except asyncio.CancelledError:
                pass
            await orchestrator.stop()

    def _signal_handler() -> None:
        orchestrator.request_shutdown()

    loop = asyncio.new_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except (ValueError, NotImplementedError):
            pass

    try:
        loop.run_until_complete(_run())
    except KeyboardInterrupt:
        pass
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.remove_signal_handler(sig)
            except (ValueError, NotImplementedError):
                pass
        loop.close()

    console.print(f"[bold green]{t('agent_exited', config)}[/bold green]")


@app.command()
def status() -> None:
    """Show Argus gateway status or collaboration tree overview."""
    config, tree = _load_config_and_tree()
    status_dir = _expand_path(config.argus.memory_dir).parent
    pid_path = status_dir / "gateway.pid"
    status_path = status_dir / "status.json"

    pid = _read_pid_file(pid_path)
    is_running = pid is not None and _is_heartbeat_fresh(status_path)

    if is_running:
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = None

        if data is None:
            console.print("[yellow]Gateway status file is unreadable.[/yellow]")
        else:
            console.print(
                f"[bold green]{t('gateway_started', config)}[/bold green] (pid: {pid}, "
                f"heartbeat: {data.get('timestamp', 'unknown')})"
            )
            table = Table(title=t("status_header", config))
            table.add_column("Node", style="cyan")
            table.add_column("Type", style="magenta")
            table.add_column("Status", style="green")

            nodes = data.get("nodes", {})
            for node in tree.nodes:
                node_status = nodes.get(node.id, {})
                if node.type == "agent":
                    running = node_status.get("running", False)
                    status_text = "[green]running[/green]" if running else "[red]stopped[/red]"
                    extra = f" model={node_status.get('model', node.model or 'default')}"
                else:
                    handler_ok = node_status.get("handler_registered", False)
                    status_text = (
                        "[green]connected[/green]" if handler_ok else "[yellow]idle[/yellow]"
                    )
                    extra = ""
                table.add_row(node.id, node.type, f"{status_text}{extra}")
            console.print(table)
    else:
        console.print(f"[bold yellow]{t('gateway_stopped', config)}[/bold yellow]")
        console.print(Rule("Collaboration Tree"))
        table = Table(title=f"{len(tree.nodes)} nodes, {len(tree.edges)} edges")
        table.add_column("ID", style="cyan")
        table.add_column("Label", style="green")
        table.add_column("Type", style="magenta")
        table.add_column("Model / Delivery", style="dim")
        for node in tree.nodes:
            detail = node.model if node.type == "agent" else str(node.delivery or "-")
            table.add_row(node.id, node.label, node.type, detail)
        console.print(table)

        reachable_table = Table(title="Reachability")
        reachable_table.add_column("From", style="cyan")
        reachable_table.add_column("Can reach", style="green")
        for node in tree.nodes:
            targets = tree.get_reachable_nodes(node.id)
            reachable_table.add_row(node.id, ", ".join(targets) if targets else "-")
        console.print(reachable_table)


if __name__ == "__main__":
    app()
