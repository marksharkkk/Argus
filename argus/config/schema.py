"""Argus configuration schema."""

from pathlib import Path
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class ArgusGuiConfig(BaseModel):
    """GUI backend host/port configuration."""

    model_config = ConfigDict(populate_by_name=True)

    host: str = "127.0.0.1"
    port: int = 18791


class ProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""

    model_config = ConfigDict(populate_by_name=True)

    api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("api_key", "apiKey"),
    )
    api_base: str | None = Field(
        default=None,
        validation_alias=AliasChoices("api_base", "apiBase"),
    )
    extra_headers: dict[str, str] | None = Field(
        default=None,
        validation_alias=AliasChoices("extra_headers", "extraHeaders"),
    )


class AgentDefaults(BaseModel):
    """Default settings for agent nodes."""

    model_config = ConfigDict(populate_by_name=True)

    model: str = "mock"
    provider: str = "mock"
    max_tokens: int = Field(
        default=2048,
        validation_alias=AliasChoices("max_tokens", "maxTokens"),
    )
    temperature: float = 0.7
    max_tool_iterations: int = Field(
        default=5,
        validation_alias=AliasChoices("max_tool_iterations", "maxToolIterations"),
    )
    context_window_tokens: int = Field(
        default=8192,
        validation_alias=AliasChoices("context_window_tokens", "contextWindowTokens"),
    )
    context_block_limit: int = Field(
        default=5,
        validation_alias=AliasChoices("context_block_limit", "contextBlockLimit"),
    )
    max_tool_result_chars: int = Field(
        default=4000,
        validation_alias=AliasChoices("max_tool_result_chars", "maxToolResultChars"),
    )
    provider_retry_mode: str = Field(
        default="simple",
        validation_alias=AliasChoices("provider_retry_mode", "providerRetryMode"),
    )
    timezone: str = "UTC"
    reasoning_effort: str | None = Field(
        default=None,
        validation_alias=AliasChoices("reasoning_effort", "reasoningEffort"),
    )


class AgentsConfig(BaseModel):
    """Agent-level configuration block."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ToolConfig(BaseModel):
    """Tool-related configuration placeholders."""

    model_config = ConfigDict(populate_by_name=True)

    web: dict[str, Any] = Field(default_factory=dict)
    exec: dict[str, Any] = Field(default_factory=dict)
    restrict_to_workspace: bool = Field(
        default=False,
        validation_alias=AliasChoices("restrict_to_workspace", "restrictToWorkspace"),
    )
    mcp_servers: list[dict[str, Any]] = Field(default_factory=list)


class ArgusExtensionConfig(BaseModel):
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
    language: str = Field(
        default="zh",
        alias="language",
        validation_alias=AliasChoices("language"),
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


class ArgusConfig(BaseModel):
    """Root configuration for Argus."""

    model_config = ConfigDict(populate_by_name=True)

    workspace: str = "~/.argus"
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    tools: ToolConfig = Field(default_factory=ToolConfig)
    argus: ArgusExtensionConfig = Field(default_factory=ArgusExtensionConfig)

    @property
    def workspace_path(self) -> Path:
        """Return the expanded workspace path."""
        return Path(self.workspace).expanduser()

    def get_provider(self, model: str | None = None) -> ProviderConfig | None:
        """Return the provider config for a model, or None if not configured."""
        provider_name = self.get_provider_name(model)
        if provider_name is None:
            return None
        return self.providers.get(provider_name)

    def get_provider_name(self, model: str | None = None) -> str | None:
        """Resolve the provider name for a model."""
        if model is None:
            return self.agents.defaults.provider
        # Model strings like "provider/model" or "provider/model/name"
        parts = model.split("/")
        if len(parts) > 1 and parts[0] in self.providers:
            return parts[0]
        return self.agents.defaults.provider

    def get_api_base(self, model: str | None = None) -> str | None:
        """Return the API base URL for a model's provider."""
        provider = self.get_provider(model)
        return provider.api_base if provider else None
