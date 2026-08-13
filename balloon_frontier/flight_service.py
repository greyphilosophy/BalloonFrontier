"""Transport-neutral flight preparation, simulation, evaluation, and rewards."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Optional

from balloon_frontier.aerostat import (
    configured_simulation_state,
    safety_notes_for_request,
)
from balloon_frontier.atmosphere import (
    AtmosphereProvider,
    current_atmosphere_provider,
    use_atmosphere,
)
from balloon_frontier.flight_score import calculate_flight_score
from balloon_frontier.launch_result import (
    FlightResult,
    LaunchRequest,
    MissionAssignment,
    MissionResult,
    telemetry_list_to_points,
)
from balloon_frontier.medal_tier import get_medal_emoji, medal_tier_to_string
from balloon_frontier.mission_evaluator import MissionEvaluator
from balloon_frontier.mission_selection import (
    assign_missions_to_flight,
    choose_mission_count,
    seed_from_game_state,
)
from balloon_frontier.powered_simulation import run_powered_simulation
from balloon_frontier.progression import PlayerRegistryRepository
from balloon_frontier.reward_service import RewardService
from balloon_frontier.simulation import SimulationState
from balloon_frontier.weather_column import generate_weather_column
from balloon_frontier.weather_event import (
    WeatherEvent,
    generate_weather,
    weather_impact_on_flight,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FlightOutcome:
    """Complete result of a flight pipeline run."""

    result: FlightResult
    score: float = 0.0
    medal_name: str = "NONE"
    medal_emoji: str = "⚪"
    weather: Optional[WeatherEvent] = None
    mission_assignment: Optional[MissionAssignment] = None
    mission_results: tuple[MissionResult, ...] = ()
    safety_notes: tuple[str, ...] = ()
    flight_notes: tuple[str, ...] = ()
    weather_impacts: dict = field(default_factory=dict)
    atmosphere_provider: AtmosphereProvider | None = None


@dataclass(frozen=True)
class LaunchPreparation:
    """Resolved simulation state and metadata for one launch."""

    request: LaunchRequest
    sim_state: SimulationState
    weather: Optional[WeatherEvent] = None
    mission_assignment: Optional[dict] = None
    wind_site_id: str = "field"
    weather_impacts: dict = field(default_factory=dict)
    atmosphere_provider: AtmosphereProvider | None = None


class FlightServiceError(Exception):
    """Raised when flight simulation fails."""


def _state_with_weather_impacts(
    state: SimulationState,
    impacts: dict,
) -> SimulationState:
    """Return a weather-adjusted state copy without mutating preparation data."""
    envelope = replace(
        state.envelope,
        weather_burst_risk_modifier=impacts.get("burst_risk", 1.0),
        weather_solar_modifier=impacts.get("thermal_efficiency", 1.0),
        weather_pressure_modifier=impacts.get("pressure_modifier", 1.0),
    )
    return replace(
        state,
        envelope=envelope,
        weather_ascent_multiplier=impacts.get("ascent_rate", 1.0),
        weather_drift_multiplier=impacts.get("drift_factor", 1.0),
    )


def _mission_results_with_flight_notes(
    mission_results: tuple[MissionResult, ...],
    flight_notes: tuple[str, ...],
) -> tuple[MissionResult, ...]:
    """Append emergent flight lessons without changing completion or rewards."""
    if not mission_results or not flight_notes:
        return mission_results
    note_text = " Flight notes: " + " ".join(flight_notes)
    return tuple(
        replace(result, explanation=result.explanation + note_text)
        for result in mission_results
    )


class FlightService:
    """Transport-neutral flight pipeline."""

    def __init__(
        self,
        default_sim_time: float = 150.0,
        mission_sim_time: float = 43200.0,
        mission_step_interval: float = 1.0,
        reward_service: Optional[RewardService] = None,
        mission_evaluator: Optional[MissionEvaluator] = None,
        atmosphere_provider: AtmosphereProvider | None = None,
    ) -> None:
        self.default_sim_time = default_sim_time
        self.mission_sim_time = mission_sim_time
        self.mission_step_interval = mission_step_interval
        self.reward_service = (
            reward_service
            if reward_service is not None
            else RewardService(PlayerRegistryRepository())
        )
        self.mission_evaluator = (
            mission_evaluator if mission_evaluator is not None else MissionEvaluator()
        )
        self.atmosphere_provider = atmosphere_provider

    def prepare(self, launch_request: LaunchRequest) -> LaunchPreparation:
        req = launch_request
        wind_site_id = req.launch_site_id
        payload_keys = list(req.payload_ids) if req.payload_ids else []
        weather_seed = seed_from_game_state(
            gas=req.gas_id,
            envelope=req.envelope_id,
            payloads=payload_keys,
            site=req.launch_site_id,
        )
        weather = generate_weather(
            site=req.launch_site_id,
            gas=req.gas_id,
            envelope=req.envelope_id,
            payloads=payload_keys,
            seed=weather_seed,
        )
        weather_column = generate_weather_column(
            weather_seed,
            scenario=_scenario_for_weather(weather),
        )
        provider = (
            current_atmosphere_provider()
            or self.atmosphere_provider
            or weather_column
        )
        with use_atmosphere(provider):
            sim_state = configured_simulation_state(
                req,
                req.to_simulation_state(),
            )

        payload_count = len(payload_keys) if payload_keys else 0
        mission_count = choose_mission_count(payload_count)
        mission_assignment = assign_missions_to_flight(
            payload_count=payload_count,
            seed=weather_seed,
            mission_count=mission_count,
            selected_payloads=payload_keys,
            launch_site=req.launch_site_id,
        )
        weather_impacts = weather_impact_on_flight(weather) if weather else {}
        return LaunchPreparation(
            request=req,
            sim_state=sim_state,
            weather=weather,
            mission_assignment=mission_assignment,
            wind_site_id=wind_site_id,
            weather_impacts=weather_impacts,
            atmosphere_provider=provider,
        )

    def run(self, launch_request: LaunchRequest) -> FlightOutcome:
        """Execute the full flight pipeline under the selected atmosphere."""
        try:
            with use_atmosphere(self.atmosphere_provider):
                return self._run_active(launch_request)
        except Exception as error:
            logger.exception("Flight simulation failed")
            raise FlightServiceError(f"Flight simulation failed: {error}") from error

    def _run_active(self, launch_request: LaunchRequest) -> FlightOutcome:
        prep = self.prepare(launch_request)
        provider = prep.atmosphere_provider
        with use_atmosphere(provider):
            return self._run_prepared(launch_request, prep, provider)

    def _run_prepared(
        self,
        launch_request: LaunchRequest,
        prep: LaunchPreparation,
        provider: AtmosphereProvider | None,
    ) -> FlightOutcome:
        sim_state = (
            _state_with_weather_impacts(prep.sim_state, prep.weather_impacts)
            if prep.weather
            else prep.sim_state
        )

        safety_notes = safety_notes_for_request(launch_request)
        assignment_dict = prep.mission_assignment or {}
        is_mission = bool(assignment_dict.get("mission_ids"))
        max_time = self.mission_sim_time if is_mission else self.default_sim_time
        max_steps = int(max_time / 0.1)
        step_interval = self.mission_step_interval if is_mission else None
        powered_result = run_powered_simulation(
            sim_state,
            payload_ids=tuple(launch_request.payload_ids),
            dt=0.1,
            total_time_s=max_time,
            max_steps=max_steps,
            step_interval=step_interval,
        )
        telemetry = list(powered_result.telemetry)
        flight_notes = powered_result.flight_notes

        mission_assignment = MissionAssignment(
            mission_ids=tuple(assignment_dict.get("mission_ids", [])),
            seed=assignment_dict.get("seed"),
        )
        if not telemetry:
            return FlightOutcome(
                result=FlightResult(telemetry=(), launch_request=launch_request),
                weather=prep.weather,
                mission_assignment=mission_assignment,
                safety_notes=safety_notes,
                flight_notes=flight_notes,
                weather_impacts=prep.weather_impacts,
                atmosphere_provider=provider,
            )

        points = telemetry_list_to_points(telemetry)
        peak_altitude_m = max((point.altitude_m for point in points), default=0.0)
        duration_s = points[-1].time_s if points else 0.0
        payload_count = max(
            1,
            len([pid for pid in launch_request.payload_ids if pid != "none"]),
        )
        score = calculate_flight_score(
            peak_altitude_m,
            payload_count,
            duration_s,
        )
        mission_results = self.mission_evaluator.evaluate(
            request=launch_request,
            telemetry=tuple(points),
            assignment=mission_assignment,
        )
        mission_results = _mission_results_with_flight_notes(
            mission_results,
            flight_notes,
        )
        if launch_request.player_id:
            mission_results = self.reward_service.apply(
                player_id=launch_request.player_id,
                mission_results=mission_results,
            )

        return FlightOutcome(
            result=FlightResult(
                telemetry=tuple(points),
                launch_request=launch_request,
            ),
            score=score,
            medal_name=medal_tier_to_string(peak_altitude_m),
            medal_emoji=get_medal_emoji(peak_altitude_m),
            weather=prep.weather,
            mission_assignment=mission_assignment,
            mission_results=mission_results,
            safety_notes=safety_notes,
            flight_notes=flight_notes,
            weather_impacts=prep.weather_impacts,
            atmosphere_provider=provider,
        )


def _scenario_for_weather(weather: WeatherEvent) -> str:
    """Keep narrative weather and the hidden vertical column broadly consistent."""
    name = weather.name.lower()
    if "jet stream" in name:
        return "jet_stream"
    if "storm" in name or weather.storm_risk >= 0.25:
        return "frontal"
    if weather.cloud_density >= 0.45 and weather.temp_anomaly_k >= 2.0:
        return "atmospheric_river"
    if weather.wind_gust_factor < 0.9:
        return "calm"
    if weather.wind_gust_factor >= 1.5:
        return "jet_stream"
    return "frontal"


flight_service = FlightService()
