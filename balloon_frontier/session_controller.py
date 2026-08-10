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
    mode: GameMode
    requires_missions: bool
    uses_progression: bool
    sandbox: bool
    mission_count: int
    description: str


_POLICIES = {
    GameMode.STORY: ModePolicy(
        GameMode.STORY,
        True,
        True,
        False,
        1,
        "Narrative play with chapter-specific missions and progression.",
    ),
    GameMode.SCENARIO: ModePolicy(
        GameMode.SCENARIO,
        True,
        False,
        False,
        3,
        "A deterministic themed mission set without story progression.",
    ),
    GameMode.FREE_PLAY: ModePolicy(
        GameMode.FREE_PLAY,
        False,
        False,
        True,
        0,
        "Unrestricted sandbox flight with no mission commitment.",
    ),
}


def _playable_mode(mode: GameMode | str | int) -> GameMode:
    parsed = mode if isinstance(mode, GameMode) else select_game_mode(mode)
    # Tutorial is retained only as a legacy enum value. It no longer selects a
    # separate mission, evaluator, weather profile, or physics path.
    return GameMode.STORY if parsed is GameMode.TUTORIAL else parsed


def get_mode_policy(mode: GameMode | str | int) -> ModePolicy:
    return _POLICIES[_playable_mode(mode)]


def _stable_seed(
    mode: GameMode,
    configuration: Mapping[str, Any],
    context: Mapping[str, Any],
) -> int:
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
    player_id: str | int | None = None,
    context: Mapping[str, Any] | None = None,
    mission_dir: str | None = None,
) -> tuple[str, ...]:
    """Assign the active Story chapter or the selected non-Story mission set."""

    policy = get_mode_policy(mode)
    if not policy.requires_missions:
        return ()

    context = dict(context or {})
    payloads = [p for p in configuration.get("payloads", ()) if p != "none"]
    site = configuration.get("site") or configuration.get("launch_site")
    ensure_missions_loaded(mission_dir)

    if policy.mode is GameMode.STORY:
        from .story_mission_select import resolve_story_mission

        mission_id = resolve_story_mission(
            str(player_id) if player_id is not None else None,
            context.get("story_mission_id"),
        )
        if mission_id not in MISSIONS:
            raise LookupError(
                f"Story mission definition {mission_id!r} is not loaded"
            )
        # Story owns its selected mission even when the player's experimental
        # configuration cannot satisfy it. The ordinary evaluator reports why.
        return (mission_id,)

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
    policy = get_mode_policy(mode)
    frozen_context = MappingProxyType(dict(context or {}))
    session = GameSession(mode=policy.mode, player_id=player_id)
    session.set_configuration(configuration)
    missions = assign_missions_for_mode(
        policy.mode,
        session.configuration,
        player_id=player_id,
        context=frozen_context,
        mission_dir=mission_dir,
    )
    session.mark_ready()
    return SessionPlan(session, policy, missions, frozen_context)


class SessionRegistry:
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
