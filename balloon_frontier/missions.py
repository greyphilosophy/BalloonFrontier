"""Balloon Frontier - Mission System

Missions define objectives, equipment/site requirements, and optional safety
constraints.  Safety constraints are game rules only: the simulator may model a
configuration that a particular mission refuses to approve.
"""

import json
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Objective:
    """A single mission objective."""
    type: str
    params: dict = field(default_factory=dict)
    description: str = ""


@dataclass
class Mission:
    """Mission definition matching GDD §14.2 format."""
    id: str
    title: str
    description: str
    launch_site: str = "field"
    budget: int = 5000
    required_payloads: List[str] = field(default_factory=list)
    objectives: List[Objective] = field(default_factory=list)
    difficulty: int = 1
    # Risk tags are supplied by components (gas, envelope, heat source).  An
    # empty list means the mission does not prohibit any simulated method.
    prohibited_risk_tags: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "launch_site": self.launch_site,
            "budget": self.budget,
            "required_payloads": self.required_payloads,
            "objectives": [{"type": o.type, "params": o.params} for o in self.objectives],
            "difficulty": self.difficulty,
            "prohibited_risk_tags": self.prohibited_risk_tags,
        }


MISSIONS: dict[str, Mission] = {}


def register_mission(mission: Mission):
    """Register a mission by ID."""
    MISSIONS[mission.id] = mission


def get_mission(mission_id: str) -> Mission:
    """Look up a mission by ID."""
    if mission_id not in MISSIONS:
        raise KeyError(f"Unknown mission: {mission_id}")
    return MISSIONS[mission_id]


def list_missions() -> List[Mission]:
    """Return all registered missions."""
    return list(MISSIONS.values())


def load_mission_json(path: str) -> Mission:
    """Load a mission from a JSON file."""
    with open(path, "r") as f:
        data = json.load(f)
    objectives = [
        Objective(
            type=o["type"],
            params=o.get("params", {}),
            description=o.get("description", ""),
        )
        for o in data.get("objectives", [])
    ]
    return Mission(
        id=data["id"],
        title=data["title"],
        description=data.get("description", ""),
        launch_site=data.get("launch_site", "field"),
        budget=data.get("budget", 5000),
        required_payloads=data.get("required_payloads", []),
        objectives=objectives,
        difficulty=data.get("difficulty", 1),
        prohibited_risk_tags=data.get("prohibited_risk_tags", []),
    )


def load_mission_directory(directory: str):
    """Load all JSON mission files from a directory."""
    for fname in os.listdir(directory):
        if fname.endswith(".json"):
            path = os.path.join(directory, fname)
            try:
                m = load_mission_json(path)
                register_mission(m)
            except (json.JSONDecodeError, KeyError, FileNotFoundError):
                pass
