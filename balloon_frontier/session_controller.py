"""Shared game-session policy, mission planning, and adapter helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from threading import RLock
from types import MappingProxyType
from typing import Any, Mapping

from .game_modes import GameMode, select_game_mode
from .game_session import GameSession
from .mission_selection import ensure_missions_loaded, select_missions
from .missions import MISSIONS


@dataclass(frozen=True)
class ModePolicy:
    """UI-agnostic behavior associated with one game mode."""

    mode: GameMode
    requires_missions: bool
    uses_progression: bool
    sandbox: bool
    mission_count: int
    description: str


_POLICIES = {
    GameMode.TUTORIAL: ModePolicy(
        GameMode.TUTORIAL, True, False, False, 1,
        "Guided first flight with a controlled introductory mission.",
    ),
    GameMode.STORY: ModePolicy(
        GameMode.STORY, True, True, False, 1,
        "Narrative play with a chapter-specific mission and progression.",
    ),
    GameMode.SCENARIO: ModePolicy(
        GameMode.SCENARIO, True, False, False, 3,
        "A deterministic themed mission set without story progression.",
    ),
    GameMode.FREE_PLAY: ModePolicy(
        GameMode.FREE_PLAY, False, False, True, 0,
        "Unrestricted sandbox flight with no mission commitment.",
    ),
}


def get_mode_policy(mode: GameMode | str | int) -> ModePolicy:
    """Return the explicit policy for a mode selection."""

    parsed = mode if isinstance(mode, GameMode) else select_game_mode(mode)
    return _POLICIES[parsed]


def _stable_seed(mode: GameMode, configuration: Mapping[str, Any], context: Mapping[str, Any]) -> int:
    payload = json.dumps(
        {"mode": mode.value, "configuration": configuration, "context": context},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:4], "big")


def _mission_matches_configuration(mission, payloads: list[str], site: str | None) -> bool:
    required = set(mission.required_payloads or ())
    site_ok = mission.launch_site is None or site is None or mission.launch_site == site
    return required.issubset(set(payloads)) and site_ok


def assign_missions_for_mode(
    mode: GameMode | str | int,
    configuration: Mapping[str, Any],
    *,
    context: Mapping[str, Any] | None = None,
    mission_dir: str | None = None,
) -> tuple[str, ...]:
    """Assign mode-appropriate missions deterministically.

    Tutorial prefers ``first_flight`` when it matches the selected setup. Story
    always assigns its current chapter, ``edge_of_space``, so invalid player
    choices fail that chapter naturally instead of silently selecting another
    mission. Scenario delegates to the generic deterministic selector, and Free
    Play intentionally returns no missions.
    """

    policy = get_mode_policy(mode)
    if not policy.requires_missions:
        return ()

    context = dict(context or {})
    payloads = [p for p in configuration.get("payloads", ()) if p != "none"]
    site = configuration.get("site") or configuration.get("launch_site")
    ensure_missions_loaded(mission_dir)

    if policy.mode is GameMode.STORY and "edge_of_space" in MISSIONS:
        return ("edge_of_space",)

    if policy.mode is GameMode.TUTORIAL and "first_flight" in MISSIONS:
        mission = MISSIONS["first_flight"]
        if _mission_matches_configuration(mission, payloads, site):
            return ("first_flight",)

    seed = _stable_seed(policy.mode, configuration, context)
    return tuple(
        select_missions(
            mission_count=policy.mission_count,
            seed=seed,
            selected_payloads=payloads,
            launch_site=site,
            mission_dir=mission_dir,
        )
    )


@dataclass(frozen=True)
class SessionPlan:
    """A configured session plus mode policy and deterministic missions."""

    session: GameSession
    policy: ModePolicy
    missions: tuple[str, ...]
    context: Mapping[str, Any]


def plan_session(
    mode: GameMode | str | int,
    configuration: Mapping[str, Any],
    *,
    player_id: str | int | None = None,
    context: Mapping[str, Any] | None = None,
    mission_dir: str | None = None,
) -> SessionPlan:
    """Create and ready a session using shared policy for every UI."""

    policy = get_mode_policy(mode)
    session = GameSession(mode=policy.mode, player_id=player_id)
    session.set_configuration(configuration)
    frozen_context = MappingProxyType(dict(context or {}))
    missions = assign_missions_for_mode(
        policy.mode,
        session.configuration,
        context=frozen_context,
        mission_dir=mission_dir,
    )
    session.mark_ready()
    return SessionPlan(session, policy, missions, frozen_context)


class SessionRegistry:
    """Thread-safe per-player session storage used by Discord and other adapters."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionPlan] = {}
        self._lock = RLock()

    def put(self, player_id: str | int, plan: SessionPlan) -> None:
        with self._lock:
            self._sessions[str(player_id)] = plan

    def get(self, player_id: str | int) -> SessionPlan | None:
        with self._lock:
            return self._sessions.get(str(player_id))

    def pop(self, player_id: str | int) -> SessionPlan | None:
        with self._lock:
            return self._sessions.pop(str(player_id), None)

    def cancel(self, player_id: str | int) -> bool:
        with self._lock:
            plan = self._sessions.pop(str(player_id), None)
        if plan is None:
            return False
        if not plan.session.is_terminal:
            plan.session.cancel()
        return True
