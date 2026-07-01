# Argus

[English](README_EN.md) | [中文](README.md)

Argus is a multi-agent collaboration orchestration platform that lets humans define the communication topology between themselves and multiple AI agents through a **Collaboration Tree**. It enables private chat, group chat, and meetings as first-class multi-agent collaboration patterns, while building an inheritable team memory system.

## Core Features

- **Collaboration Tree Orchestration**: declare nodes (human / agent) and directed/bidirectional communication edges with YAML/JSON; the collaboration topology is fully user-defined.
- **Private / Group / Broadcast Chat**: single chat, `@mention` group chat, and `@all` broadcasting are routed according to the Collaboration Tree, unreachable nodes are filtered automatically.
- **Meeting Engine**: automatically notify participants, request agent speeches in round-robin order, broadcast speeches, enter free discussion, and archive meeting minutes.
- **Five-Layer Memory Inheritance**: project memory, team best practices, agent growth profiles, meeting archive library, and collaboration pattern library, with recommendations for historical collaboration trees based on project type.
- **Real LLM Driver**: connect to DeepSeek, OpenAI, and other OpenAI-compatible APIs; agents actively communicate within the Collaboration Tree using the `argus_send_message` tool.
- **Visual GUI**: a Tauri 2.0 + Vue 3 desktop client supporting drag-and-drop collaboration tree editing, chat view, meeting view, and status panel.
- **CLI Gateway**: command-line entry points `argus onboard` / `argus gateway` / `argus agent` / `argus status`.
- **Mock Mode**: `scripts/start_gui_for_demo.py` starts the system with zero API cost, suitable for demos and screenshots.

## Showcase

To quickly understand what Argus can do, see [docs/showcase_en.md](docs/showcase_en.md). Below is a preview of the main GUI screens:

| Tree Editor | Node Chat |
|-------------|-----------|
| ![Tree](docs/images/screenshots/argus-gui-tree.png) | ![Chat](docs/images/screenshots/argus-gui-chat.png) |

| Meeting View | Status Panel |
|--------------|--------------|
| ![Meeting](docs/images/screenshots/argus-gui-meeting.png) | ![Status](docs/images/screenshots/argus-gui-status.png) |

## Quick Install

Requires Python 3.11+.

```bash
git clone https://github.com/marksharkkk/argus.git
cd argus
pip install -e .
```

After installation, you will have the `argus` package and the `argus` CLI entry point.

## Quick Start

### 1. Initialize Workspace

```bash
argus onboard
```

This creates the default config, sample collaboration tree, and five-layer memory directories under `~/.argus/`.

If you prefer not to use `argus onboard`, you can manually create a workspace and copy the sample configs:

```bash
mkdir my-argus-workspace
cp config/example_config.json my-argus-workspace/config.json
cp config/example_tree.yaml my-argus-workspace/collaboration_tree.yaml
```

Then edit `config.json` and replace `providers.deepseek.apiKey` with your real API key.

### 2. Inspect and Edit the Collaboration Tree

```bash
# View current reachability
argus status

# Edit ~/.argus/collaboration_tree.yaml
```

The sample collaboration tree contains three nodes: `human`, `dev`, and `writer`, connected bidirectionally.

### 3. Start the Gateway

```bash
argus gateway
```

Gateway loads the config, starts all agent nodes, launches the GUI backend HTTP/WebSocket service, and keeps running until you press `Ctrl+C`.

### 4. Interact as a Human Node

```bash
argus agent --node human -m "@dev hi, please take a look at this requirement"
```

### 5. Use the GUI

Open `http://127.0.0.1:18792` (default port) in your browser to use the collaboration tree editor, chat view, and meeting view.

## Project Structure

```
argus/
├── argus/                  # Argus main package
│   ├── adapters/           # Agent runtime adapter layer
│   ├── cli/                # Typer CLI
│   ├── config/             # Config schema and loaders
│   ├── core/               # Collaboration tree, message bus, router, meeting engine, orchestrator
│   ├── gui/                # GUI backend FastAPI/UVicorn service
│   └── memory/             # Five-layer memory storage
├── gui/                    # Tauri 2.0 + Vue 3 desktop frontend
├── config/                 # Sample collaboration tree configs
├── memory/                 # Sample memory directories
├── tests/                  # Unit and end-to-end tests
│   ├── cli/
│   ├── core/
│   ├── e2e/
│   └── gui/
├── docs/                   # Documentation
├── pyproject.toml
└── README.md
```

## Running Tests

```bash
python -m pytest tests -q
```

End-to-end tests are in `tests/e2e/`, using Fake Agents and temporary directories. They do not call real LLMs and do not affect `~/.argus`.

### Verify Human Meeting Takeover and Inbox Persistence

The repository provides an LLM-free end-to-end validation script to quickly confirm human-node related features:

```bash
NO_LLM=1 python scripts/validate_human_features.py
```

This script will:
1. Start a real Orchestrator (using mock agents, no API cost).
2. Verify that messages sent to an offline human are persisted to the inbox and automatically drained upon reconnection.
3. Verify that a human can `skip_turn`, `update_topic`, and `close` during a meeting.

For real LLM validation, remove `NO_LLM=1` and ensure a valid API key is configured in `config.json`.

## Development Notes

- `.mock-argus/`, `.real-test-argus/`, runtime logs, GUI build artifacts, and Python caches are excluded in `.gitignore` and will not be committed.
- Sample config is in `config/example_config.json`; the API key is a placeholder and must be replaced before use.
- The GUI frontend builds successfully with `npm run build`; launching the Tauri desktop window requires a local Rust toolchain.

## License

MIT License
