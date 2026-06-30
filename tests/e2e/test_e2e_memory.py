"""End-to-end test for the Argus five-layer memory store."""

from __future__ import annotations

from pathlib import Path

import pytest

from argus.memory.store import MemoryStore


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "memory")


def test_project_memory_round_trip(store: MemoryStore, tmp_path: Path) -> None:
    """Saving and loading a project memory writes the expected Markdown file."""
    store.save_project(
        "demo",
        {
            "name": "Demo Project",
            "status": "active",
            "body": "A sample project used for end-to-end tests.",
            "task_history": [
                {"summary": "Initial setup", "timestamp": "2026-06-29T10:00:00"}
            ],
        },
    )

    project_path = tmp_path / "memory" / "projects" / "demo.md"
    assert project_path.exists()

    loaded = store.load_project("demo")
    assert loaded["project_id"] == "demo"
    assert loaded["name"] == "Demo Project"
    assert loaded["status"] == "active"


def test_team_best_practice_append(store: MemoryStore, tmp_path: Path) -> None:
    """Best-practice entries are appended to the team memory file."""
    store.append_best_practice(
        {
            "title": "Review before merge",
            "category": "Process",
            "content": "Every pull request must be reviewed by at least one peer.",
        }
    )

    content = store.load_best_practices()
    assert "Review before merge" in content
    assert "Every pull request" in content


def test_agent_profile_update(store: MemoryStore, tmp_path: Path) -> None:
    """Agent profiles persist stats, skills, and timestamps."""
    store.update_agent_profile(
        "dev-agent",
        {
            "tasks_completed": 12,
            "success_rate": 0.92,
            "skills": ["python", "typescript", "fastapi"],
            "avg_duration_sec": 45.5,
        },
    )

    profile_path = tmp_path / "memory" / "agents" / "dev-agent.md"
    assert profile_path.exists()

    profile = store.load_agent_profile("dev-agent")
    assert profile["agent_id"] == "dev-agent"
    assert profile["tasks_completed"] == 12
    assert profile["success_rate"] == 0.92
    assert "python" in profile["skills"]
    assert profile["last_updated"]


def test_meeting_archive(store: MemoryStore, tmp_path: Path) -> None:
    """Meeting transcripts are archived by date."""
    store.save_meeting(
        "2026-06-29",
        {
            "topic": "Daily Standup",
            "organizer": "human",
            "participants": ["human", "dev"],
            "messages": [
                {
                    "speaker": "human",
                    "text": "What is the progress?",
                    "timestamp": "2026-06-29T10:00:00",
                },
                {
                    "speaker": "dev",
                    "text": "Feature is ready for review.",
                    "timestamp": "2026-06-29T10:05:00",
                },
            ],
        },
    )

    meeting_path = tmp_path / "memory" / "meetings" / "2026-06-29.md"
    assert meeting_path.exists()
    assert "2026-06-29" in store.list_meetings()

    loaded = store.load_meeting("2026-06-29")
    assert loaded["date"] == "2026-06-29"


def test_mode_library_recommendation(store: MemoryStore, tmp_path: Path) -> None:
    """Modes can be saved, rated, and recommended by project type."""
    store.save_mode(
        "python-team",
        {
            "metadata": {"project_types": ["web", "backend"], "description": "Python team"},
            "nodes": [
                {"id": "human", "label": "Human", "type": "human"},
                {"id": "dev", "label": "Developer", "type": "agent", "agent_id": "dev"},
            ],
            "edges": [{"from": "human", "to": "dev", "bidirectional": True}],
        },
    )

    store.rate_mode("python-team", 4.5, "Works well for web projects.")
    store.rate_mode("python-team", 5.0, "Excellent for backend services.")

    mode_path = tmp_path / "memory" / "modes" / "python-team.yaml"
    assert mode_path.exists()
    assert "python-team" in store.list_modes()

    recommended = store.recommend_mode("web")
    assert recommended is not None
    assert recommended["name"] == "python-team"
    ratings = recommended.get("ratings", [])
    assert len(ratings) == 2
    assert sum(r["score"] for r in ratings) / len(ratings) == 4.75

    # Unrelated project types should yield no recommendation.
    assert store.recommend_mode("mobile") is None
