"""Collaboration tree data model for Argus."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Node(BaseModel):
    """A node in the collaboration tree."""

    id: str
    label: str
    type: Literal["human", "agent"]
    agent_id: str | None = None
    model: str | None = None
    delivery: dict | None = None
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_agent_id(self) -> "Node":
        if self.type == "agent" and not self.agent_id:
            raise ValueError(f"agent node '{self.id}' must have agent_id")
        return self


class Edge(BaseModel):
    """A directed communication channel between two nodes."""

    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    bidirectional: bool = False


class CollaborationTree(BaseModel):
    """A collaboration tree defining who can communicate with whom."""

    nodes: list[Node]
    edges: list[Edge]

    @model_validator(mode="after")
    def validate_references_and_duplicates(self) -> "CollaborationTree":
        node_ids = {node.id for node in self.nodes}
        directed_edges: set[tuple[str, str]] = set()

        for edge in self.edges:
            if edge.from_ not in node_ids:
                raise ValueError(f"edge references unknown node: {edge.from_}")
            if edge.to not in node_ids:
                raise ValueError(f"edge references unknown node: {edge.to}")

            pair = (edge.from_, edge.to)
            if pair in directed_edges:
                raise ValueError(f"duplicate directed edge: {edge.from_} -> {edge.to}")
            directed_edges.add(pair)

            if edge.bidirectional and edge.from_ != edge.to:
                reverse = (edge.to, edge.from_)
                if reverse in directed_edges:
                    raise ValueError(f"duplicate directed edge: {edge.to} -> {edge.from_}")
                directed_edges.add(reverse)

        return self

    @property
    def _directed_edges(self) -> set[tuple[str, str]]:
        edges: set[tuple[str, str]] = set()
        for edge in self.edges:
            edges.add((edge.from_, edge.to))
            if edge.bidirectional and edge.from_ != edge.to:
                edges.add((edge.to, edge.from_))
        return edges

    @classmethod
    def from_dict(cls, data: dict) -> "CollaborationTree":
        """Parse a collaboration tree from a dictionary."""
        if not isinstance(data, dict):
            raise TypeError("collaboration tree data must be a dict")
        return cls.model_validate(data)

    @classmethod
    def from_file(cls, path: str | Path) -> "CollaborationTree":
        """Load a collaboration tree from a YAML or JSON file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"collaboration tree file not found: {path}")

        suffix = path.suffix.lower()
        with path.open("r", encoding="utf-8") as f:
            if suffix in (".yaml", ".yml"):
                data = yaml.safe_load(f)
            elif suffix == ".json":
                data = json.load(f)
            else:
                raise ValueError(f"unsupported collaboration tree file format: {suffix}")

        if not isinstance(data, dict):
            raise ValueError("collaboration tree file must contain a dict")
        return cls.from_dict(data)

    def to_dict(self) -> dict:
        """Serialize the collaboration tree to a dictionary."""
        return self.model_dump(by_alias=True)

    def save(self, path: str | Path) -> None:
        """Save the collaboration tree to a YAML or JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        suffix = path.suffix.lower()
        data = self.to_dict()

        with path.open("w", encoding="utf-8") as f:
            if suffix in (".yaml", ".yml"):
                yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
            elif suffix == ".json":
                json.dump(data, f, ensure_ascii=False, indent=2)
            else:
                raise ValueError(f"unsupported collaboration tree file format: {suffix}")

    def can_communicate(self, from_id: str, to_id: str) -> bool:
        """Return True if a directed edge exists from ``from_id`` to ``to_id``."""
        return (from_id, to_id) in self._directed_edges

    def get_reachable_nodes(self, from_id: str) -> list[str]:
        """Return node IDs reachable from ``from_id`` via one direct edge."""
        return sorted(to_id for f, to_id in self._directed_edges if f == from_id)

    def get_node(self, node_id: str) -> Node | None:
        """Return the node with the given ID, or None if not found."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None


_MENTION_RE = re.compile(r"@([A-Za-z0-9_-]+)")


def parse_mentions(text: str) -> list[str]:
    """Extract ``@node_id`` mentions from text."""
    return _MENTION_RE.findall(text)
