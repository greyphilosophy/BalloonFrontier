"""Balloon Frontier - Mission System

Implements the mission definition format from GDD §14.2 and §17.
Missions define objectives, constraints, and evaluation criteria for flights.

Each mission can be loaded from a JSON data file for content expansion.
"""

import json
import os
from dataclasses import dataclass, field
from typing import List

@dataclass
class Objective:
    """A single mission objective."""
    type: str  # "reach_altitude", "capture_photo", "recover_data", etc.
    params: dict = field(default_factory=dict)

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
    difficulty: int = 1  # 1-5 scale

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
    with open(path, 'r') as f:
        data = json.load(f)
    objectives = [Objective(type=o['type'], params=o.get('params', {})) 
                  for o in data.get('objectives', [])]
    return Mission(
        id=data['id'],
        title=data['title'],
        description=data.get('description', ''),
        launch_site=data.get('launch_site', 'field'),
        budget=data.get('budget', 5000),
        required_payloads=data.get('required_payloads', []),
        objectives=objectives,
        difficulty=data.get('difficulty', 1),
    )

def load_mission_directory(directory: str):
    """Load all JSON mission files from a directory."""
    for fname in os.listdir(directory):
        if fname.endswith('.json'):
            path = os.path.join(directory, fname)
            try:
                m = load_mission_json(path)
                register_mission(m)
            except (json.JSONDecodeError, KeyError, FileNotFoundError):
                pass
