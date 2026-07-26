"""Transport-neutral flight preparation, simulation, evaluation, and rewards."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from balloon_frontier.atmosphere import AtmosphereProvider, use_atmosphere
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
from balloon_frontier.progression import PlayerRegistryRepository
from balloon_frontier.reward_service import RewardService
from balloon_frontier.simulation import (
    SimulationState,
    run_simulation as run_full_simulation,
)
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
    weather_impacts: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LaunchPreparation:
    """Resolved simulation state and metadata for one launch."""

    request: LaunchRequest
    sim_state: SimulationState
    weather: Optional[WeatherEvent] = None
    mission_assignment: Optional[dict] = None
    wind_site_id: str = "field"
    weather_impacts: dict = field(default_factory=dict)


class FlightServiceError(Exception):
    """Raised when flight simulation fails."""


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
        sim_state = req.to_simulation_state()
        payload_keys = list(req.payload_ids) if req.payload_ids else []
        weather = generate_weather(
            site=req.launch_site_id,
            gas=req.gas_id,
            envelope=req.envelope_id,
            payloads=payload_keys,
            seed=seed_from_game_state(
                gas=req.gas_id,
                envelope=req.envelope_id,
                payloads=payload_keys,
                site=req.launch_site_id,
            ),
        )

        payload_count = len(payload_keys) if payload_keys else 0
        mission_count = choose_mission_count(payload_count)
        mission_seed = seed_from_game_state(
            gas=req.gas_id,
            envelope=req.envelope_id,
            payloads=payload_keys,
            site=req.launch_site_id,
        )
        mission_assignment = assign_missions_to_flight(
            payload_count=payload_count,
            seed=mission_seed,
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

        if prep.weather:
            impacts = prep.weather_impacts
            prep.sim_state.envelope.weather_burst_risk_modifier = impacts.get(
                "burst_risk", 1.0
            )
            prep.sim_state.envelope.weather_solar_modifier = impacts.get(
                "thermal_efficiency", 1.0
            )
            # Profiles store the base atmospheric field while the associated
            # WeatherEvent stores launch-specific modifiers. Applying both recreates
            # the original conditions without baking weather policy into the data.
            prep.sim_state.envelope.weather_pressure_modifier = impacts.get(
                "pressure_modifier", 1.0
            )
            prep.sim_state.weather_ascent_multiplier = impacts.get(
                "ascent_rate", 1.0
            )
            prep.sim_state.weather_drift_multiplier = impacts.get(
                "drift_factor", 1.0
            )

        assignment_dict = prep.mission_assignment or {}
        is_mission = bool(assignment_dict.get("mission_ids"))
        max_time = self.mission_sim_time if is_mission else self.default_sim_time
        max_steps = int(max_time / 0.1)
        step_interval = self.mission_step_interval if is_mission else None
        telemetry = run_full_simulation(
            prep.sim_state,
            dt=0.1,
            total_time_s=max_time,
            max_steps=max_steps,
            step_interval=step_interval,
        )

        mission_assignment = MissionAssignment(
            mission_ids=tuple(assignment_dict.get("mission_ids", [])),
            seed=assignment_dict.get("seed"),
        )
        if not telemetry:
            return FlightOutcome(
                result=FlightResult(telemetry=(), launch_request=launch_request),
                weather=prep.weather,
                mission_assignment=mission_assignment,
                weather_impacts=prep.weather_impacts,
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
            weather_impacts=prep.weather_impacts,
        )


flight_service = FlightService()
