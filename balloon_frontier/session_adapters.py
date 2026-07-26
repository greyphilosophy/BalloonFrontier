"""Thin UI adapters around the shared session controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .game_modes import GameMode
from .game_session import SessionState
from .session_controller import SessionPlan, SessionRegistry, plan_session


def configuration_from_launch_request(request: Any) -> dict[str, Any]:
    """Translate a LaunchRequest-like object into shared session configuration."""

    return {
        "gas": request.gas_id,
        "envelope": request.envelope_id,
        "balloon_size": getattr(request, "balloon_size", None),
        "payloads": tuple(request.payload_ids),
        "site": request.launch_site_id,
        "fill_mode": request.fill_mode.value,
        "manual_gas_mass_kg": getattr(request, "manual_gas_mass_kg", None),
    }


def prepare_cli_session(
    mode: GameMode | str | int,
    request: Any,
    *,
    player_id: str | int | None = None,
) -> SessionPlan:
    """Create the shared plan used by the terminal game before launch."""

    return plan_session(
        mode,
        configuration_from_launch_request(request),
        player_id=player_id,
        context={"ui": "cli"},
    )


def configuration_from_discord_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Translate Discord configurator state into shared configuration keys."""

    return {
        "gas": state.get("gas"),
        "envelope": state.get("envelope"),
        "balloon_size": state.get("balloon_size"),
        "payloads": tuple(state.get("payloads") or ()),
        "site": state.get("site"),
        "fill_mode": state.get("fill_mode", "auto"),
        "manual_gas_mass_kg": state.get("manual_gas_mass"),
    }


@dataclass
class DiscordSessionAdapter:
    """Manage isolated Discord sessions for DM and guild interactions."""

    registry: SessionRegistry

    @classmethod
    def create(cls) -> "DiscordSessionAdapter":
        return cls(SessionRegistry())

    def start(
        self,
        player_id: str | int,
        mode: GameMode | str | int,
        state: Mapping[str, Any],
        *,
        channel_kind: str = "dm",
    ) -> SessionPlan:
        existing = self.registry.get(player_id)
        if existing is not None and not existing.session.is_terminal:
            existing.session.cancel()

        plan = plan_session(
            mode,
            configuration_from_discord_state(state),
            player_id=player_id,
            context={"ui": "discord", "channel": channel_kind},
        )
        self.registry.put(player_id, plan)
        return plan

    def launch(self, player_id: str | int) -> SessionPlan:
        plan = self._require(player_id)
        plan.session.launch()
        return plan

    def complete(self, player_id: str | int, result: Any) -> SessionPlan:
        plan = self._require(player_id)
        plan.session.complete(result)
        return plan

    def cancel(self, player_id: str | int) -> bool:
        return self.registry.cancel(player_id)

    def _require(self, player_id: str | int) -> SessionPlan:
        plan = self.registry.get(player_id)
        if plan is None:
            raise ValueError("no active session for player")
        if plan.session.state is SessionState.CANCELLED:
            raise ValueError("session is cancelled")
        return plan
