"""Argus five-layer memory store."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


class MemoryStore:
    """Persistent memory store for Argus projects, team, agents, meetings and modes."""

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)
        for name in ("projects", "team", "agents", "meetings", "modes"):
            (self.base_dir / name).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def _write_text(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")

    def _parse_frontmatter(self, text: str) -> dict[str, Any]:
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return {}
        try:
            end = lines[1:].index("---") + 1
        except ValueError:
            return {}
        fm_text = "\n".join(lines[1:end])
        return yaml.safe_load(fm_text) or {}

    def _build_frontmatter_doc(self, data: dict[str, Any], title: str, body: str = "") -> str:
        fm = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        parts = ["---", fm.rstrip(), "---", f"# {title}"]
        if body:
            parts.append("")
            parts.append(body.rstrip())
        return "\n".join(parts) + "\n"

    def _now_iso(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    # ------------------------------------------------------------------
    # Project memory
    # ------------------------------------------------------------------
    def save_project(self, project_id: str, data: dict) -> None:
        path = self.base_dir / "projects" / f"{project_id}.md"
        data = dict(data)
        body = data.pop("body", None) or ""
        history = data.pop("task_history", [])
        history_lines = ["## Task History", ""]
        for item in history:
            if isinstance(item, dict):
                summary = item.get("summary", "")
                ts = item.get("timestamp", "")
                line = f"- [{ts}] {summary}" if ts else f"- {summary}"
            else:
                line = f"- {item}"
            history_lines.append(line)
        if not history:
            history_lines.append("_No tasks recorded yet._")
        full_body = body + "\n\n" + "\n".join(history_lines) if body else "\n".join(history_lines)
        doc = self._build_frontmatter_doc(data, f"Project: {project_id}", full_body)
        self._write_text(path, doc)

    def load_project(self, project_id: str) -> dict:
        path = self.base_dir / "projects" / f"{project_id}.md"
        text = self._read_text(path)
        data = self._parse_frontmatter(text)
        data["project_id"] = project_id
        return data

    def list_projects(self) -> list[str]:
        return sorted(p.stem for p in (self.base_dir / "projects").glob("*.md"))

    # ------------------------------------------------------------------
    # Team memory
    # ------------------------------------------------------------------
    def _append_team_entry(self, path: Path, entry: dict) -> None:
        ts = entry.get("timestamp") or self._now_iso()
        title = entry.get("title", "")
        content = entry.get("content", "")
        category = entry.get("category", "General")
        lines = [f"\n## {category}\n"]
        if title:
            lines.append(f"**{title}**  ")
        lines.append(f"*Recorded at {ts}*  ")
        lines.append(content)
        if not path.exists():
            path.write_text("", encoding="utf-8")
        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def append_best_practice(self, entry: dict) -> None:
        path = self.base_dir / "team" / "best_practices.md"
        self._append_team_entry(path, entry)

    def append_lesson(self, entry: dict) -> None:
        path = self.base_dir / "team" / "lessons_learned.md"
        self._append_team_entry(path, entry)

    def load_best_practices(self) -> str:
        path = self.base_dir / "team" / "best_practices.md"
        return self._read_text(path) if path.exists() else ""

    def load_lessons(self) -> str:
        path = self.base_dir / "team" / "lessons_learned.md"
        return self._read_text(path) if path.exists() else ""

    # ------------------------------------------------------------------
    # Agent profile
    # ------------------------------------------------------------------
    def update_agent_profile(self, agent_id: str, stats: dict) -> None:
        path = self.base_dir / "agents" / f"{agent_id}.md"
        current: dict[str, Any] = {}
        if path.exists():
            current = self._parse_frontmatter(self._read_text(path))
        fields = {
            "tasks_completed": 0,
            "success_rate": 0.0,
            "skills": [],
            "avg_duration_sec": 0.0,
            "last_updated": "",
        }
        for key, default in fields.items():
            current.setdefault(key, default)
        for key, value in stats.items():
            current[key] = value
        current["last_updated"] = self._now_iso()
        body = (
            "## Skills\n\n"
            + "\n".join(f"- {s}" for s in current.get("skills", []))
            + "\n\n## Notes\n\n_Agent profile managed by Argus._"
        )
        doc = self._build_frontmatter_doc(current, f"Agent: {agent_id}", body)
        self._write_text(path, doc)

    def load_agent_profile(self, agent_id: str) -> dict:
        path = self.base_dir / "agents" / f"{agent_id}.md"
        text = self._read_text(path)
        data = self._parse_frontmatter(text)
        data.setdefault("tasks_completed", 0)
        data.setdefault("success_rate", 0.0)
        data.setdefault("skills", [])
        data.setdefault("avg_duration_sec", 0.0)
        data.setdefault("last_updated", "")
        data["agent_id"] = agent_id
        return data

    # ------------------------------------------------------------------
    # Meeting archive
    # ------------------------------------------------------------------
    def save_meeting(self, date_str: str | None, transcript: dict) -> None:
        date = date_str or datetime.now().strftime("%Y-%m-%d")
        path = self.base_dir / "meetings" / f"{date}.md"
        transcript = dict(transcript)
        body = transcript.pop("body", None) or ""
        transcript_lines = ["## Transcript", ""]
        messages = transcript.pop("messages", [])
        for msg in messages:
            if isinstance(msg, dict):
                speaker = msg.get("speaker", "Unknown")
                text = msg.get("text", "")
                ts = msg.get("timestamp", "")
                line = f"**{speaker}** ({ts}): {text}" if ts else f"**{speaker}**: {text}"
            else:
                line = f"- {msg}"
            transcript_lines.append(line)
        if not messages:
            transcript_lines.append("_No messages recorded._")
        full_body = body + "\n\n" + "\n".join(transcript_lines) if body else "\n".join(transcript_lines)
        doc = self._build_frontmatter_doc(transcript, f"Meeting: {date}", full_body)
        self._write_text(path, doc)

    def load_meeting(self, date_str: str) -> dict:
        path = self.base_dir / "meetings" / f"{date_str}.md"
        text = self._read_text(path)
        data = self._parse_frontmatter(text)
        data["date"] = date_str
        return data

    def list_meetings(self) -> list[str]:
        return sorted(p.stem for p in (self.base_dir / "meetings").glob("*.md"))

    # ------------------------------------------------------------------
    # Mode library
    # ------------------------------------------------------------------
    def save_mode(self, name: str, tree: dict) -> None:
        path = self.base_dir / "modes" / f"{name}.yaml"
        tree.setdefault("ratings", [])
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(tree, f, allow_unicode=True, sort_keys=False)

    def load_mode(self, name: str) -> dict:
        path = self.base_dir / "modes" / f"{name}.yaml"
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def list_modes(self) -> list[str]:
        return sorted(p.stem for p in (self.base_dir / "modes").glob("*.yaml"))

    def rate_mode(self, name: str, score: float, feedback: str) -> None:
        path = self.base_dir / "modes" / f"{name}.yaml"
        data = self.load_mode(name) if path.exists() else {}
        ratings = data.setdefault("ratings", [])
        ratings.append(
            {
                "score": score,
                "feedback": feedback,
                "timestamp": self._now_iso(),
            }
        )
        self.save_mode(name, data)

    def recommend_mode(self, project_type: str) -> dict | None:
        best: dict | None = None
        best_avg = -1.0
        for name in self.list_modes():
            data = self.load_mode(name)
            metadata = data.get("metadata", {})
            types = metadata.get("project_types", [])
            if project_type not in types:
                continue
            ratings = data.get("ratings", [])
            avg = sum(r["score"] for r in ratings) / len(ratings) if ratings else 0.0
            if avg > best_avg:
                best_avg = avg
                best = {"name": name, **data}
        return best
