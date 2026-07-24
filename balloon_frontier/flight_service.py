"""Balloon Frontier — Flight Service

Transport-neutral service that takes a LaunchRequest, runs the simulation,
and returns a FlightResult with all downstream effects (missions, weather,
scoring, medals).

This replaces the inline launch logic currently in:
- `_LaunchButton.callback` in discord_bot.py
- `cmd_launch` in discord_bot.py (the /launch prefix command)

The service does NOT produce Discord embeds or CLI output — those belong
to the transport layer (discord_bot.py / cli_game.py).

## Usage

```python
from balloon_frontier.launch_result import LaunchRequest
from balloon_frontier.flight_service import flight_service

req = LaunchRequest(...)
result = flight_service.run(req)

# Access the result
print(f"Peak altitude: {result.peak_altitude_m} m")
print(f"Burst: {result.burst}")
print(f"Telemetry points: {len(result.telemetry)}")
```
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from balloon_frontier.weather_event import WeatherEvent

from balloon_frontier.launch_result import (
    LaunchRequest,
    FlightResult,
    TelemetryPoint,
    telemetry_list_to_points,
    MissionAssignment,
    MissionResult,
)
from balloon_frontier.simulation import (
    run_simulation as run_full_simulation,
    EnvelopeConfig,
    SimulationState,
)
from balloon_frontier.weather_event import (
    generate_weather,
    weather_impact_on_flight,
)
from balloon_frontier.mission_selection import (
    assign_missions_to_flight,
    seed_from_game_state,
    choose_mission_count,
)
from balloon_frontier.flight_score import calculate_flight_score
from balloon_frontier.medal_tier import get_medal_emoji, medal_tier_to_string
from balloon_frontier.reward_service import RewardService
from balloon_frontier.progression import PlayerRegistryRepository


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FlightOutcome:
    """Complete result of a flight pipeline run.

    Wraps the simulation result with all metadata needed by transport layers
    (Discord embeds, CLI output, progression updates) without requiring a
    second prepare() call.

    Attributes:
        result: The FlightResult with telemetry.
        score: Flight score (computed from peak altitude, payload count, duration).
        medal_name: Medal tier name (e.g. "BRONZE", "SILVER", "GOLD", "PLATINUM").
        medal_emoji: Emoji representation of the medal tier (e.g. "🥉", "🥈", "🥇", "💎").
        weather: The generated weather event.
        mission_assignment: Assigned missions for this flight (typed).
        mission_results: Evaluation results for each assigned mission.
        weather_impacts: Computed weather impact modifiers.
    """
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
    """Intermediate result of preparing a launch.

    Attributes:
        request: The original launch request.
        sim_state: The SimulationState ready for the engine.
        weather: Generated weather event (if applicable).
        mission_assignment: Assigned missions (if applicable).
        wind_site_id: Site wind profile identifier.
        weather_impacts: Computed weather impact modifiers (burst_risk, etc.).
    """
    request: LaunchRequest
    sim_state: SimulationState
    weather: Optional[WeatherEvent] = None
    mission_assignment: Optional[dict] = None
    wind_site_id: str = "field"
    weather_impacts: dict = field(default_factory=dict)


class FlightServiceError(Exception):
    """Raised when flight simulation fails."""
    pass


class FlightService:
    """Transport-neutral flight pipeline.

    Attributes:
        default_sim_time: Default simulation duration in seconds (non-mission).
        mission_sim_time: Default simulation duration for mission flights.
        mission_step_interval: Store only 1 sample per second for mission flights.
    """

    def __init__(
        self,
        default_sim_time: float = 150.0,
        mission_sim_time: float = 43200.0,  # 12 hours
        mission_step_interval: float = 1.0,
        reward_service: Optional[RewardService] = None,
    ) -> None:
        self.default_sim_time = default_sim_time
        self.mission_sim_time = mission_sim_time
        self.mission_step_interval = mission_step_interval
        self.reward_service = (
            reward_service
            if reward_service is not None
            else RewardService(PlayerRegistryRepository())
        )

    def prepare(self, launch_request: LaunchRequest) -> LaunchPreparation:
        """Prepare a launch: resolve catalog, build SimulationState, assign missions & weather.

        Args:
            launch_request: The player's launch configuration.

        Returns:
            LaunchPreparation with all resolved data.
        """
        req = launch_request
        wind_site_id = req.launch_site_id

        # Build SimulationState from the launch request
        sim_state = req.to_simulation_state()

        # Generate weather based on launch configuration
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

        # Assign missions
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

        # Compute weather impacts (applied in run())
        if weather:
            weather_impacts = weather_impact_on_flight(weather)
        else:
            weather_impacts = {}

        return LaunchPreparation(
            request=req,
            sim_state=sim_state,
            weather=weather,
            mission_assignment=mission_assignment,
            wind_site_id=wind_site_id,
            weather_impacts=weather_impacts,
        )

    def run(
        self,
        launch_request: LaunchRequest,
    ) -> FlightOutcome:
        """Execute the full flight pipeline.

        Args:
            launch_request: The player's launch configuration.

        Returns:
            FlightResult with complete telemetry and metadata.

        Raises:
            FlightServiceError: If simulation fails.
        """
        try:
            # Prepare the launch (resolve catalog, weather, missions)
            prep = self.prepare(launch_request)

            # Apply weather impacts to the simulation state
            if prep.weather:
                impacts = prep.weather_impacts
                # Apply all weather modifiers to the envelope config and state
                prep.sim_state.envelope.weather_burst_risk_modifier = impacts.get('burst_risk', 1.0)
                prep.sim_state.envelope.weather_solar_modifier = impacts.get('thermal_efficiency', 1.0)
                prep.sim_state.envelope.weather_pressure_modifier = impacts.get('pressure_modifier', 1.0)
                prep.sim_state.weather_ascent_multiplier = impacts.get('ascent_rate', 1.0)
                prep.sim_state.weather_drift_multiplier = impacts.get('drift_factor', 1.0)

            # Determine simulation duration based on actual mission count
            # Only explicitly-mission flights (with mission_ids in assignment) use
            # mission_sim_time. Regular Discord/CLI launches use default_sim_time.
            assignment_dict = prep.mission_assignment or {}
            is_mission = bool(assignment_dict.get("mission_ids"))
            max_time = self.mission_sim_time if is_mission else self.default_sim_time
            max_steps = int(max_time / 0.1)

            # Run simulation
            step_interval = self.mission_step_interval if is_mission else None
            tel_full = run_full_simulation(
                prep.sim_state,
                dt=0.1,
                total_time_s=max_time,
                max_steps=max_steps,
                step_interval=step_interval,
            )

            if not tel_full:
                # Empty telemetry — return result with zeroed values
                mission_ids_tuple = tuple(assignment_dict.get("mission_ids", []))
                mission_assign = MissionAssignment(
                    mission_ids=mission_ids_tuple,
                    seed=assignment_dict.get("seed"),
                )
                result = FlightOutcome(
                    result=FlightResult(
                        telemetry=(),
                        launch_request=launch_request,
                    ),
                    score=0.0,
                    medal_name="NONE",
                    medal_emoji="⚪",
                    weather=prep.weather,
                    mission_assignment=mission_assign,
                    mission_results=(),
                    weather_impacts=prep.weather_impacts,
                )
                return result

            # Convert raw telemetry dicts to TelemetryPoint objects
            points = telemetry_list_to_points(tel_full)

            # Compute peak altitude and duration from telemetry (before building FlightResult)
            peak_altitude_m = max((tp.altitude_m for tp in points), default=0.0)
            duration_s = points[-1].time_s if points else 0.0

            # Convert dict assignment to typed MissionAssignment
            mission_ids_tuple = tuple(assignment_dict.get("mission_ids", []))
            mission_assign = MissionAssignment(
                mission_ids=mission_ids_tuple,
                seed=assignment_dict.get("seed"),
            )

            # Compute score and medal from result properties
            payload_count = max(1, len([pid for pid in launch_request.payload_ids if pid != "none"]))
            score = calculate_flight_score(
                peak_altitude_m,
                payload_count,
                duration_s,
            )
            medal_name = medal_tier_to_string(peak_altitude_m)
            medal_emoji = get_medal_emoji(peak_altitude_m)

            # Evaluate missions
            mission_results = self._evaluate_missions(
                telemetry=tuple(points),
                mission_assignment=mission_assign,
                launch_request=launch_request,
            )

            # Apply mission rewards to player progression (if player_id provided)
            if launch_request.player_id:
                mission_results = self.reward_service.apply(
                    player_id=launch_request.player_id,
                    mission_results=mission_results,
                )

            # Build FlightOutcome with all metadata
            result = FlightOutcome(
                result=FlightResult(
                    telemetry=tuple(points),
                    launch_request=launch_request,
                ),
                score=score,
                medal_name=medal_name,
                medal_emoji=medal_emoji,
                weather=prep.weather,
                mission_assignment=mission_assign,
                mission_results=mission_results,
                weather_impacts=prep.weather_impacts,
            )

            return result

        except Exception as e:
            logger.exception("Flight simulation failed")
            raise FlightServiceError(f"Flight simulation failed: {e}") from e

    def _evaluate_missions(
        self,
        telemetry: tuple[TelemetryPoint, ...],
        mission_assignment: MissionAssignment,
        launch_request: LaunchRequest,
    ) -> tuple[MissionResult, ...]:
        """Evaluate mission completion based on flight results.

        Args:
            telemetry: Flight telemetry data.
            mission_assignment: The assigned missions.
            launch_request: The original launch configuration.

        Returns:
            Tuple of MissionResult objects.
        """
        from balloon_frontier.missions import MISSIONS

        if not mission_assignment.mission_ids:
            return ()

        results: list[MissionResult] = []
        peak_altitude = max((tp.altitude_m for tp in telemetry), default=0.0)
        duration = telemetry[-1].time_s if telemetry else 0.0
        has_landed = any(tp.landed for tp in telemetry)
        has_crashed = any(tp.crashed for tp in telemetry)
        burst = any(tp.burst for tp in telemetry)

        for mission_id in mission_assignment.mission_ids:
            mission = MISSIONS.get(mission_id)
            if mission is None:
                results.append(MissionResult(
                    mission_id=mission_id,
                    completed=False,
                    reward=0,
                    explanation=f"Mission {mission_id} not found",
                ))
                continue

            # Enforce mission configuration requirements before objective evaluation
            selected = set(launch_request.payload_ids) - {"none"}
            required = set(mission.required_payloads)
            if not required.issubset(selected):
                missing = required - selected
                results.append(MissionResult(
                    mission_id=mission_id,
                    completed=False,
                    reward=0,
                    explanation=f"Mission {mission_id} failed: missing required payloads: {', '.join(sorted(missing))}",
                ))
                continue

            if launch_request.launch_site_id != mission.launch_site:
                results.append(MissionResult(
                    mission_id=mission_id,
                    completed=False,
                    reward=0,
                    explanation=f"Mission {mission_id} failed: launch site {launch_request.launch_site_id!r} does not match required site {mission.launch_site!r}",
                ))
                continue

            completed = self._check_mission_completion(
                mission=mission,
                peak_altitude=peak_altitude,
                duration=duration,
                has_landed=has_landed,
                has_crashed=has_crashed,
                burst=burst,
                telemetry=telemetry,
                mission_id=mission_id,
                launch_request=launch_request,
            )

            reward = mission.budget if completed else 0
            explanation = self._generate_mission_explanation(
                mission=mission,
                completed=completed,
                peak_altitude=peak_altitude,
            )

            results.append(MissionResult(
                mission_id=mission_id,
                completed=completed,
                reward=reward,
                explanation=explanation,
            ))

        return tuple(results)

    def _check_mission_completion(
        self,
        mission,
        peak_altitude: float,
        duration: float,
        has_landed: bool,
        has_crashed: bool,
        burst: bool,
        telemetry: tuple,
        mission_id: str,
        launch_request,
    ) -> bool:
        """Check if a mission's objectives were completed.

        Handles every objective type present in the mission catalog:
        - reach_altitude: peak altitude >= minimum_m
        - recover_data: landed and not crashed
        - capture_photo: payload has camera and photo quality sufficient
        - float_duration: flight duration >= target hours
        - station_keep: balloon stayed near target altitude for sufficient steps
        - fly_distance: horizontal travel >= minimum_m

        Unknown objective types fail closed.
        """
        # Pre-compute horizontal distance travelled (for fly_distance)
        if telemetry and len(telemetry) > 1:
            start_x = telemetry[0].x_m
            end_x = telemetry[-1].x_m
            distance_travelled_m = abs(end_x - start_x)
        else:
            distance_travelled_m = 0.0

        for objective in mission.objectives:
            obj_type = objective.type

            if obj_type == "reach_altitude":
                minimum_m = objective.params.get('minimum_m', 0)
                if peak_altitude < minimum_m:
                    return False

            elif obj_type == "recover_data":
                if not has_landed or has_crashed:
                    return False

            elif obj_type == "capture_photo":
                # Photo capture requires camera payload in launch config
                selected_local = set(launch_request.payload_ids) - {"none"}
                if "camera" not in selected_local:
                    return False
                # Quality scales with altitude up to the target quality threshold
                min_quality = objective.params.get('minimum_quality', 0.5)
                quality = min(peak_altitude / 50000.0, 1.0)
                if burst:
                    quality *= 0.5
                if quality < min_quality:
                    return False

            elif obj_type == "float_duration":
                target_hours = objective.params.get('target_hours', 0)
                actual_hours = duration / 3600.0
                if actual_hours < target_hours:
                    return False

            elif obj_type == "station_keep":
                # Station keep: percentage of steps within ±500m of target
                target_alt = objective.params.get('target_altitude_m', 0)
                tolerance = 500.0
                in_range_steps = sum(
                    1 for tp in telemetry
                    if abs(tp.altitude_m - target_alt) <= tolerance
                )
                max_steps = max(len(telemetry), 1)
                fraction = in_range_steps / max_steps
                # Require at least 50% of steps in station-keeping range
                if fraction < 0.5:
                    return False

            elif obj_type == "fly_distance":
                # Horizontal distance must be >= minimum_m requirement
                minimum_m = objective.params.get('minimum_m', 0)
                if distance_travelled_m < minimum_m:
                    return False

            else:
                # Unknown objective types fail closed with logging
                logger.error(
                    "Unsupported mission objective type '%s' in mission '%s'. "
                    "Objective will cause mission failure.",
                    obj_type,
                    getattr(mission, 'id', mission_id),
                )
                return False

        return True

    def _generate_mission_explanation(
        self,
        mission,
        completed: bool,
        peak_altitude: float,
    ) -> str:
        """Generate a human-readable explanation for mission result."""
        if completed:
            return f"Mission {mission.title} completed! Budget {mission.budget} credits awarded."
        else:
            return f"Mission {mission.title} not completed. No budget awarded."


# Module-level singleton
flight_service = FlightService()