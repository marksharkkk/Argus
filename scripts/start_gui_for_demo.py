"""启动 Argus GUI 演示服务（mock 模式，不消耗 LLM API）。

同时启动：
- GUI 后端 API/WebSocket：http://127.0.0.1:18792
- 静态前端服务：http://127.0.0.1:18793

访问：
    http://127.0.0.1:18793

按 Ctrl+C 停止。
"""

from __future__ import annotations

import asyncio
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from argus.config.loader import load_argus_config
from argus.config.schema import ArgusConfig
from argus.core.orchestrator import ArgusOrchestrator
from argus.core.tree import CollaborationTree
from argus.gui.server import start_gui_server
from argus.memory.store import MemoryStore


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "config" / "example_config.json"
TREE_PATH = BASE_DIR / "config" / "example_tree.yaml"
STATIC_DIR = BASE_DIR / "gui" / "dist"


def start_static_server(host: str, port: int, directory: Path) -> threading.Thread:
    """Start a simple HTTP server for the static frontend build."""
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(
        *args, directory=str(directory), **kwargs
    )
    server = socketserver.TCPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


async def main() -> int:
    config = load_argus_config(CONFIG_PATH)
    tree = CollaborationTree.from_file(TREE_PATH)
    memory_store = MemoryStore(Path(config.argus.memory_dir).expanduser())

    orchestrator = ArgusOrchestrator(
        config=config,
        tree=tree,
        memory_store=memory_store,
        mock=True,
    )

    await orchestrator.start()

    api_host = config.argus.api_host
    api_port = config.argus.api_port
    gui_server = start_gui_server(orchestrator, api_host, api_port)
    await gui_server.start()

    static_host = api_host
    static_port = api_port + 1
    start_static_server(static_host, static_port, STATIC_DIR)

    print(f"Argus GUI demo running:")
    print(f"  API/WebSocket: http://{api_host}:{api_port}")
    print(f"  Web UI:        http://{static_host}:{static_port}")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await gui_server.stop()
        await orchestrator.stop()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)
