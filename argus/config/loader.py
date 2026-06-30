"""Argus configuration loading utilities."""

import json
import os
from pathlib import Path
from typing import Any

import pydantic
from loguru import logger

from argus.config.schema import ArgusConfig

ARGUS_CONFIG_PATH = Path.home() / ".argus" / "config.json"


def get_argus_config_path() -> Path:
    """Return the Argus configuration file path.

    The path can be overridden at runtime by setting the ``ARGUS_CONFIG_PATH``
    environment variable, which is useful for testing and CI environments.
    """
    env_path = os.environ.get("ARGUS_CONFIG_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return ARGUS_CONFIG_PATH


def _default_config() -> ArgusConfig:
    """Return a fresh default Argus configuration."""
    return ArgusConfig()


def load_argus_config(path: Path | None = None) -> ArgusConfig:
    """
    Load Argus configuration from a JSON file.

    If the file does not exist, a default configuration is created, saved, and
    returned. If the file exists but is invalid or cannot be parsed, a warning
    is logged and the default configuration is returned.

    Pydantic validation merges any missing fields with their defaults, so partial
    configs are upgraded automatically.
    """
    target_path = path or get_argus_config_path()

    if not target_path.exists():
        config = _default_config()
        save_argus_config(config, target_path)
        return config

    try:
        with open(target_path, encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
        config = ArgusConfig.model_validate(data)
    except (json.JSONDecodeError, ValueError, pydantic.ValidationError) as exc:
        logger.warning(f"Failed to load Argus config from {target_path}: {exc}")
        logger.warning("Using default Argus configuration.")
        config = _default_config()

    return config


def save_argus_config(config: ArgusConfig, path: Path | None = None) -> None:
    """
    Save an Argus configuration to a JSON file.

    The parent directory is created if it does not exist. Argus extension fields
    are serialized using their snake_case keys (``collaboration_tree``,
    ``memory_dir``, ``gui.host``, etc.).
    """
    target_path = path or get_argus_config_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(mode="json", by_alias=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
