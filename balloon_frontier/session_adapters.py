"""Thin UI adapters around the shared session controller."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from .flight_service import FlightService
from .game_modes import GameMode
from .game_session import SessionState
from .session_controller import SessionPlan, SessionRegistry, plan_session


class _NoOpRewardService:
    """Leave mission results untouched until tutorial evaluation is complete."""

    def apply(self, *, player_id: str, mission_results: tuple) -> tuple:
        return mission_results


def configuration_from_launch_request(request: Any) -> dict[str, Any]:
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
    return plan_session(
        mode,
        configuration_from_launch_request(request),
        player_id=player_id,
        context={"ui": "cli"},
    )


class _PlannedFlightService(FlightService):
    def __init__(
        self,
        source: FlightService,
        plan: SessionPlan,
        *,
        apply_rewards: bool = True,
    ) -> None:
        super().__init__(
            default_sim_time=source.default_sim_time,
            mission_sim_time=source.mission_sim_time,
            mission_step_interval=source.mission_step_interval,
            reward_service=source.reward_service if apply_rewards else _NoOpRewardService(),
            mission_evaluator=source.mission_evaluator,
        )
        self._source = source
        self._plan = plan

    def prepare(self, launch_request: Any) -> Any:
        preparation = self._source.prepare(launch_request)
        assignment = {
            "mission_ids": list(self._plan.missions),
            "missions": list(self._plan.missions),
            "mission_count": len(self._plan.missions),
            "seed": None,
        }
        return replace(preparation, mission_assignment=assignment)


@dataclass
class SessionAwareFlightService:
    """Wrap a FlightService so real UI launches obey the shared lifecycle."""

    service: FlightService
    mode: GameMode | str | int
    ui: str
    channel_kind: str | None = None
    on_finished: Callable[[], None] | None = None
    last_plan: SessionPlan | None = None

    def run(self, request: Any) -> Any:
        context = {"ui": self.ui}
        if self.channel_kind is not None:
            context["channel"] = self.channel_kind
        plan = plan_session(
            self.mode,
            configuration_from_launch_request(request),
            player_id=getattr(request, "player_id", None),
            context=context,
        )
        self.last_plan = plan
        plan.session.launch()
        try:
            is_tutorial = plan.session.mode is GameMode.TUTORIAL
            outcome = _PlannedFlightService(
                self.service,
                plan,
                apply_rewards=not is_tutorial,
            ).run(request)
            if is_tutorial:
                from .tutorial import evaluate_tutorial_outcome

                outcome = evaluate_tutorial_outcome(request, outcome)
                if request.player_id:
                    final_results = self.service.reward_service.apply(
                        player_id=request.player_id,
                        mission_results=outcome.mission_results,
                    )
                    outcome = replace(outcome, mission_results=final_results)
            plan.session.complete(outcome)
            return outcome
        except Exception:
            if not plan.session.is_terminal:
                plan.session.cancel()
            raise
        finally:
            if self.on_finished is not None:
                self.on_finished()


def configuration_from_discord_state(state: Mapping[str, Any]) -> dict[str, Any]:
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
