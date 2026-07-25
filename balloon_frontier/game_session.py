"""Balloon Frontier — Game session + mode selection.

This module is the shared, UI-agnostic controller layer for deciding:
- which game mode a player is in (Tutorial / Story / Scenario / Free Play)
- whether the mode should run mission-style long simulations
- which missions (if any) are assigned for the flight in that mode

Both the Discord and CLI frontends should call into this module to create
session plans and obtain mission assignments.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, List, Optional, Sequence

from .launch_result import LaunchRequest, MissionAssignment, FillMode
from .mission_selection import (
    choose_mission_count,
    seed_from_game_state,
    select_missions,
)

# Keep these aligned with FlightService defaults.
DEFAULT_SIM_TIME_S = 150.0
MISSION_SIM_TIME_S = 43200.0  # 12 hours


class GameMode(str, Enum):
    """High-level game mode selection."""

    TUTORIAL = "tutorial"
    STORY = "story"
    SCENARIO = "scenario"
    FREE_PLAY = "free_play"

    @property
    def label(self) -> str:
        return {
            GameMode.TUTORIAL: "Tutorial",
            GameMode.STORY: "Story",
            GameMode.SCENARIO: "Scenario",
            GameMode.FREE_PLAY: "Free Play",
        }[self]

    @property
    def description(self) -> str:
        return {
            GameMode.TUTORIAL: "A short, low-stakes first flight.",
            GameMode.STORY: "A narrative run with mission objectives.",
            GameMode.SCENARIO: "A mission run with a themed objective set.",
            GameMode.FREE_PLAY: "Sandbox flight — no mission commitments.",
        }[self]

    @property
    def missions_enabled(self) -> bool:
        return self in {GameMode.STORY, GameMode.SCENARIO}

    @property
    def simulation_duration_s(self) -> float:
        return MISSION_SIM_TIME_S if self.missions_enabled else DEFAULT_SIM_TIME_S


@dataclass(frozen=True, slots=True)
class GameModePolicy:
    mode: GameMode
    missions_enabled: bool
    simulation_duration_s: float


@dataclass(frozen=True, slots=True)
class GameSession:
    """UI-agnostic game session state.

    This object is intentionally lightweight: it doesn't embed any
    Discord/CLI prompting logic.
    """

    player_id: Optional[str]
    mode: GameMode

    def policy(self) -> GameModePolicy:
        return GameModePolicy(
            mode=self.mode,
            missions_enabled=self.mode.missions_enabled,
            simulation_duration_s=self.mode.simulation_duration_s,
        )

    def simulation_duration_s(self) -> float:
        return self.mode.simulation_duration_s

    def plan_mission_assignment(
        self,
        launch_request: LaunchRequest,
        *,
        seed: Optional[int] = None,
        mission_count: Optional[int] = None,
    ) -> MissionAssignment:
        """Compute mission assignment for this session/mode.

        Mission selection is deterministic when `seed` is not provided.
        """

        policy = self.policy()
        if not policy.missions_enabled:
            return MissionAssignment(mission_ids=(), seed=seed)

        selected_payloads = [pid for pid in launch_request.payload_ids if pid != "none"]
        payload_count = len(selected_payloads)
        if mission_count is None:
            mission_count = choose_mission_count(payload_count)

        resolved_seed = (
            seed
            if seed is not None
            else seed_from_game_state(
                gas=launch_request.gas_id,
                envelope=launch_request.envelope_id,
                payloads=selected_payloads,
                site=launch_request.launch_site_id,
            )
        )

        mission_ids = select_missions(
            mission_count=mission_count,
            seed=resolved_seed,
            selected_payloads=selected_payloads,
            launch_site=launch_request.launch_site_id,
        )

        return MissionAssignment(mission_ids=tuple(mission_ids), seed=resolved_seed)


_GAME_MODE_ORDER: Sequence[GameMode] = (
    GameMode.TUTORIAL,
    GameMode.STORY,
    GameMode.SCENARIO,
    GameMode.FREE_PLAY,
)


def list_game_modes() -> List[GameMode]:
    """Return modes in the canonical display order."""

    return list(_GAME_MODE_ORDER)


def select_game_mode(value: str | int) -> GameMode:
    """Coerce a CLI/Discord selection into a :class:`GameMode`.

    Accepted inputs:
    - integer indices 1..4 (Tutorial..Free Play)
    - case-insensitive strings: tutorial/story/scenario/free_play
    - case-insensitive strings: "free play" / "free-play"

    Raises:
        ValueError: if the input can't be mapped.
    """

    if isinstance(value, int):
        idx = value
        if 1 <= idx <= len(_GAME_MODE_ORDER):
            return _GAME_MODE_ORDER[idx - 1]
        raise ValueError(f"Invalid game mode index: {value}")

    s = str(value).strip().lower()
    s = s.replace("-", "_").replace(" ", "_")

    if s in {"tutorial"}:
        return GameMode.TUTORIAL
    if s in {"story"}:
        return GameMode.STORY
    if s in {"scenario"}:
        return GameMode.SCENARIO
    if s in {"free_play", "freeplay", "free_play_mode", "freeplay_mode"}:
        return GameMode.FREE_PLAY
    if s in {"free", "sandbox"}:
        return GameMode.FREE_PLAY

    raise ValueError(f"Invalid game mode selection: {value!r}")
