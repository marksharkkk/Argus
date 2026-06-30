"""Tests for the Argus CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from argus.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect Path.home() to a temporary directory for onboard tests."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


def test_onboard_creates_workspace(runner: CliRunner, mock_home: Path) -> None:
    """argus onboard creates the expected directories and files."""
    result = runner.invoke(app, ["onboard"])

    assert result.exit_code == 0, result.output

    argus_dir = mock_home / ".argus"
    memory_dir = argus_dir / "memory"

    assert argus_dir.exists()
    assert (argus_dir / "config.json").exists()
    assert (argus_dir / "collaboration_tree.yaml").exists()

    for layer in ("projects", "team", "agents", "meetings", "modes"):
        assert (memory_dir / layer).exists()

    assert (memory_dir / "team" / "best_practices.md").exists()
    assert (memory_dir / "team" / "lessons_learned.md").exists()


def test_onboard_config_uses_snake_case_fields(runner: CliRunner, mock_home: Path) -> None:
    """The generated config.json uses snake_case Argus extension keys."""
    result = runner.invoke(app, ["onboard"])
    assert result.exit_code == 0, result.output

    config_path = mock_home / ".argus" / "config.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    argus = data.get("argus", {})

    assert "collaboration_tree" in argus
    assert "memory_dir" in argus
    assert "gui" in argus
    assert isinstance(argus["gui"], dict)
    assert "host" in argus["gui"]
    assert "port" in argus["gui"]
    assert "collaborationTree" not in argus
    assert "memoryDir" not in argus


def test_onboard_is_idempotent(runner: CliRunner, mock_home: Path) -> None:
    """Running onboard twice does not fail or overwrite existing files."""
    runner.invoke(app, ["onboard"])
    config_mtime = (mock_home / ".argus" / "config.json").stat().st_mtime
    tree_mtime = (mock_home / ".argus" / "collaboration_tree.yaml").stat().st_mtime

    result = runner.invoke(app, ["onboard"])

    assert result.exit_code == 0, result.output
    assert (mock_home / ".argus" / "config.json").stat().st_mtime == config_mtime
    assert (mock_home / ".argus" / "collaboration_tree.yaml").stat().st_mtime == tree_mtime


def test_cli_help(runner: CliRunner) -> None:
    """Top-level --help lists all commands."""
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "onboard" in result.output
    assert "gateway" in result.output
    assert "agent" in result.output
    assert "status" in result.output
