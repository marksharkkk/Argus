"""Argus configuration schema extending nanobot."""

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from nanobot.config.schema import Base, Config


class ArgusGuiConfig(BaseModel):
    """GUI backend host/port configuration."""

    model_config = ConfigDict(populate_by_name=True)

    host: str = "127.0.0.1"
    port: int = 18791


class ArgusExtensionConfig(Base):
    """Argus-specific configuration extension.

    Fields are serialized with snake_case keys (e.g. ``collaboration_tree``,
    ``memory_dir``, ``gui.host``) to match the project checklist/spec. Legacy
    camelCase keys are still accepted when loading existing configs.
    """

    model_config = ConfigDict(alias_generator=None, populate_by_name=True)

    collaboration_tree: str = Field(
        default="~/.argus/collaboration_tree.yaml",
        alias="collaboration_tree",
        validation_alias=AliasChoices("collaboration_tree", "collaborationTree"),
    )
    memory_dir: str = Field(
        default="~/.argus/memory",
        alias="memory_dir",
        validation_alias=AliasChoices("memory_dir", "memoryDir"),
    )
    gui: ArgusGuiConfig = Field(default_factory=ArgusGuiConfig)
    api_host: str = Field(
        default="127.0.0.1",
        alias="api_host",
        validation_alias=AliasChoices("api_host", "apiHost"),
    )
    api_port: int = Field(
        default=18792,
        alias="api_port",
        validation_alias=AliasChoices("api_port", "apiPort"),
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_keys(cls, data: Any) -> Any:
        """Accept legacy camelCase / flat keys and migrate them to the new layout."""
        if not isinstance(data, dict):
            return data

        migrated = dict(data)

        # Top-level camelCase -> snake_case
        if "collaborationTree" in migrated and "collaboration_tree" not in migrated:
            migrated["collaboration_tree"] = migrated.pop("collaborationTree")
        if "memoryDir" in migrated and "memory_dir" not in migrated:
            migrated["memory_dir"] = migrated.pop("memoryDir")
        if "apiHost" in migrated and "api_host" not in migrated:
            migrated["api_host"] = migrated.pop("apiHost")
        if "apiPort" in migrated and "api_port" not in migrated:
            migrated["api_port"] = migrated.pop("apiPort")

        # Flat guiHost/guiPort -> nested gui.host/gui.port
        gui = migrated.get("gui")
        if not isinstance(gui, dict):
            gui = {}
        gui = dict(gui)

        if "host" not in gui:
            if "guiHost" in migrated:
                gui["host"] = migrated.pop("guiHost")
            elif "gui_host" in migrated:
                gui["host"] = migrated.pop("gui_host")
        if "port" not in gui:
            if "guiPort" in migrated:
                gui["port"] = migrated.pop("guiPort")
            elif "gui_port" in migrated:
                gui["port"] = migrated.pop("gui_port")

        migrated["gui"] = gui
        return migrated


class ArgusConfig(Config):
    """Root configuration for Argus, extends nanobot's Config."""

    argus: ArgusExtensionConfig = Field(default_factory=ArgusExtensionConfig)
