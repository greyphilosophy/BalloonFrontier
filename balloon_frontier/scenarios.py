"""Balloon Frontier — Scenario System

This module defines declarative scenario definitions and a lightweight
scenario session for tracking scenario-local objective completion.

Key invariants:
- No duplicate game state: ScenarioSession stores the caller-provided
  game_state reference as-is.
- Objective progress is scenario-local (ScenarioSession-owned), never copied
  into the global game state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class ScenarioDefinition:
    """Declarative scenario definition.

    This is intentionally small and transport-neutral: it describes
    scenario identity and which objective ids belong to the scenario.
    """

    scenario_id: str
    title: str = ""
    objective_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Prevent duplicate objective ids from being silently collapsed by
        # ScenarioSession's objective_complete dict.
        if len(set(self.objective_ids)) != len(self.objective_ids):
            raise ValueError("Scenario objective IDs must be unique")


@dataclass
class ScenarioSession:
    """Scenario runtime state.

    Stores:
    - The caller-provided ``game_state`` reference (no deep copy).
    - Scenario-local objective completion state.

    ``objective_complete`` may be supplied by callers to restore progress.
    Any missing objective ids are treated as incomplete (False). Any unknown
    objective ids are rejected.
    """

    game_state: Any
    definition: ScenarioDefinition
    objective_complete: Dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        known_ids = set(self.definition.objective_ids)

        # If the caller didn't supply progress, initialize everything to False.
        if not self.objective_complete:
            self.objective_complete = {
                oid: False for oid in self.definition.objective_ids
            }
            return

        unknown_ids = set(self.objective_complete) - known_ids
        if unknown_ids:
            raise ValueError(f"Unknown objective IDs: {sorted(unknown_ids)}")

        # Fill any missing known objective ids with False and preserve the
        # caller-provided values for known ids.
        self.objective_complete = {
            objective_id: bool(self.objective_complete.get(objective_id, False))
            for objective_id in self.definition.objective_ids
        }

    @property
    def scenario_id(self) -> str:
        return self.definition.scenario_id

    def is_objective_complete(self, objective_id: str) -> bool:
        if objective_id not in self.objective_complete:
            raise KeyError(objective_id)
        return self.objective_complete[objective_id]

    def mark_objective_complete(self, objective_id: str) -> None:
        if objective_id not in self.objective_complete:
            raise KeyError(objective_id)
        self.objective_complete[objective_id] = True

    def mark_objective_incomplete(self, objective_id: str) -> None:
        if objective_id not in self.objective_complete:
            raise KeyError(objective_id)
        self.objective_complete[objective_id] = False
