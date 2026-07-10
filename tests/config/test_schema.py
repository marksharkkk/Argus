"""Tests for the Argus configuration schema and loader."""

from __future__ import annotations

import json
from pathlib import Path

from argus.config.loader import load_argus_config, save_argus_config
from argus.config.schema import ArgusConfig


def test_default_config_serializes_snake_case(tmp_path: Path) -> None:
    """A default ArgusConfig serializes with snake_case argus keys."""
    config = ArgusConfig()
    path = tmp_path / "config.json"
    save_argus_config(config, path)

    data = json.loads(path.read_text(encoding="utf-8"))
    argus = data["argus"]

    assert argus["collaboration_tree"] == "~/.argus/collaboration_tree.yaml"
    assert argus["memory_dir"] == "~/.argus/memory"
    assert argus["gui"] == {"host": "127.0.0.1", "port": 18791}
    assert "collaborationTree" not in argus
    assert "memoryDir" not in argus
    assert "guiHost" not in argus
    assert "guiPort" not in argus


def test_legacy_camel_case_config_still_loads(tmp_path: Path) -> None:
    """An existing camelCase config is loaded and migrated to the new layout."""
    legacy = {
        "argus": {
            "collaborationTree": "/old/tree.yaml",
            "memoryDir": "/old/memory",
            "guiHost": "0.0.0.0",
            "guiPort": 8080,
            "apiHost": "0.0.0.0",
            "apiPort": 8081,
        }
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")

    config = load_argus_config(path)

    assert config.argus.collaboration_tree == "/old/tree.yaml"
    assert config.argus.memory_dir == "/old/memory"
    assert config.argus.gui.host == "0.0.0.0"
    assert config.argus.gui.port == 8080
    assert config.argus.api_host == "0.0.0.0"
    assert config.argus.api_port == 8081


def test_legacy_flat_gui_keys_migrated(tmp_path: Path) -> None:
    """Legacy flat gui_host/gui_port keys are migrated into the nested gui object."""
    legacy = {
        "argus": {
            "collaboration_tree": "tree.yaml",
            "memory_dir": "memory",
            "gui_host": "192.168.1.1",
            "gui_port": 9090,
        }
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")

    config = load_argus_config(path)

    assert config.argus.gui.host == "192.168.1.1"
    assert config.argus.gui.port == 9090


def test_nested_gui_keys_take_precedence_over_legacy(tmp_path: Path) -> None:
    """Nested gui.host/port win when both old and new keys are present."""
    data = {
        "argus": {
            "collaboration_tree": "tree.yaml",
            "memory_dir": "memory",
            "gui": {"host": "10.0.0.1", "port": 3000},
            "guiHost": "0.0.0.0",
            "guiPort": 4000,
        }
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    config = load_argus_config(path)

    assert config.argus.gui.host == "10.0.0.1"
    assert config.argus.gui.port == 3000
