"""Thin UI adapters around the shared session controller."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from .atmosphere import AtmosphereProvider, StandardAtmosphereProvider
from .flight_service import FlightService
from .game_modes import GameMode
from .game_session import SessionState
from .session_controller import SessionPlan, SessionRegistry, plan_session
from .weather_event import WeatherEvent, weather_impact_on_flight


TUTORIAL_WEATHER = WeatherEvent(
    wind_gust_factor=0.7,
    temp_anomaly_k=0.0,
    cloud_density=0.0,
    pressure_offset_pa=0.0,
    storm_risk=0.0,
    name="Calm Tutorial Conditions",
    description=(
        "Clear skies and a gentle breeze provide predictable conditions "
        "for the first flight."
    ),
    flight_modifier="calm winds",
)


class _NoOpRewardService:
    def apply(self, *, player_id: str, mission_results: tuple) -> tuple:
        return mission_results


def configuration_from_launch_request(request: Any) -> dict[str, Any]:
    return {
        "gas": request.gas_id,
        "envelope": request.envelope_id,
        "balloon_size": getattr(request, "balloon_size", None),
        "balloon_count": getattr(request, "balloon_count", 1),
        "payloads": tuple(request.payload_ids),
        "site": request.launch_site_id,
        "fill_mode": request.fill_mode.value,
        "manual_gas_mass_kg": getattr(request, "manual_gas_mass_kg", None),
    }


def prepare_cli_session(mode, request: Any, *, player_id=None) -> SessionPlan:
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
        weather_override=None,
        atmosphere_provider: AtmosphereProvider | None = None,
    ) -> None:
        super().__init__(
            default_sim_time=source.default_sim_time,
            mission_sim_time=source.mission_sim_time,
            mission_step_interval=source.mission_step_interval,
            reward_service=(
                source.reward_service if apply_rewards else _NoOpRewardService()
            ),
            mission_evaluator=source.mission_evaluator,
            atmosphere_provider=atmosphere_provider,
        )
        self._source = source
        self._plan = plan
        self._weather_override = weather_override

    def prepare(self, launch_request: Any) -> Any:
        preparation = self._source.prepare(launch_request)
        assignment = {
            "mission_ids": list(self._plan.missions),
            "missions": list(self._plan.missions),
            "mission_count": len(self._plan.missions),
            "seed": None,
        }
        changes = {"mission_assignment": assignment}
        if self._weather_override is not None:
            changes["weather"] = self._weather_override
            changes["weather_impacts"] = weather_impact_on_flight(
                self._weather_override
            )
        return replace(preparation, **changes)


@dataclass
class SessionAwareFlightService:
    service: FlightService
    mode: GameMode | str | int
    ui: str
    channel_kind: str | None = None
    on_finished: Callable[[], None] | None = None
    last_plan: SessionPlan | None = None
    story_player_id: str | None = None

    def run(self, request: Any) -> Any:
        player_id = getattr(request, "player_id", None) or self.story_player_id
        context = {"ui": self.ui}
        if self.channel_kind is not None:
            context["channel"] = self.channel_kind
        plan = plan_session(
            self.mode,
            configuration_from_launch_request(request),
            player_id=player_id,
            context=context,
        )
        self.last_plan = plan
        plan.session.launch()
        atmosphere_repository = None
        locked_profile = None
        atmosphere_provider = None
        try:
            is_tutorial = plan.session.mode is GameMode.TUTORIAL
            if player_id and not is_tutorial:
                from .atmosphere_profile import (
                    RecordedAtmosphereProvider,
                    atmosphere_profiles,
                )

                atmosphere_repository = atmosphere_profiles
                locked_profile = atmosphere_repository.get_locked_profile(
                    str(player_id)
                )
                if locked_profile is not None and locked_profile.layers:
                    atmosphere_provider = RecordedAtmosphereProvider(
                        locked_profile,
                        wind_fallback=StandardAtmosphereProvider(
                            site_id=request.launch_site_id,
                            wind_enabled=True,
                        ),
                    )

            weather_override = (
                TUTORIAL_WEATHER
                if is_tutorial
                else locked_profile.weather if locked_profile is not None else None
            )

            simulation_request = request
            if is_tutorial and request.envelope_id == "mylar":
                from .tutorial_catalog import TUTORIAL_ENVELOPE_ID

                simulation_request = replace(
                    request,
                    envelope_id=TUTORIAL_ENVELOPE_ID,
                )

            outcome = _PlannedFlightService(
                self.service,
                plan,
                apply_rewards=not is_tutorial,
                weather_override=weather_override,
                atmosphere_provider=atmosphere_provider,
            ).run(simulation_request)
            if is_tutorial:
                from .tutorial import evaluate_tutorial_outcome

                outcome = evaluate_tutorial_outcome(request, outcome)
                if player_id:
                    final_results = self.service.reward_service.apply(
                        player_id=str(player_id),
                        mission_results=outcome.mission_results,
                    )
                    outcome = replace(outcome, mission_results=final_results)
            elif plan.session.mode is GameMode.STORY:
                from .story import add_story_results

                outcome = add_story_results(
                    outcome,
                    str(player_id) if player_id else None,
                )
            if locked_profile is not None and atmosphere_repository is not None:
                atmosphere_repository.consume_locked_profile(str(player_id))
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
        "balloon_count": state.get("balloon_count", 1),
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
        player_id,
        mode,
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

    def launch(self, player_id) -> SessionPlan:
        plan = self._require(player_id)
        plan.session.launch()
        return plan

    def complete(self, player_id, result: Any) -> SessionPlan:
        plan = self._require(player_id)
        plan.session.complete(result)
        return plan

    def cancel(self, player_id) -> bool:
        return self.registry.cancel(player_id)

    def _require(self, player_id) -> SessionPlan:
        plan = self.registry.get(player_id)
        if plan is None:
            raise ValueError("no active session for player")
        if plan.session.state is SessionState.CANCELLED:
            raise ValueError("session is cancelled")
        return plan
