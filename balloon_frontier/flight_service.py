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


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FlightOutcome:
    """Complete result of a flight pipeline run.

    Wraps the simulation result with all metadata needed by transport layers
    (Discord embeds, CLI output, progression updates) without requiring a
    second prepare() call.

    Attributes:
        result: The FlightResult with telemetry.
        weather: The generated weather event.
        mission_assignment: The mission assignment dictionary.
        weather_impacts: Computed weather impact modifiers.
    """
    result: FlightResult
    weather: Optional[WeatherEvent] = None
    mission_assignment: Optional[dict] = None
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
    ) -> None:
        self.default_sim_time = default_sim_time
        self.mission_sim_time = mission_sim_time
        self.mission_step_interval = mission_step_interval

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
            assignment = prep.mission_assignment or {}
            is_mission = bool(assignment.get("mission_ids"))
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
                result = FlightOutcome(
                    result=FlightResult(
                        telemetry=(),
                        launch_request=launch_request,
                    ),
                    weather=prep.weather,
                    mission_assignment=assignment,
                    weather_impacts=prep.weather_impacts,
                )
                return result

            # Convert raw telemetry dicts to TelemetryPoint objects
            points = telemetry_list_to_points(tel_full)

            # Build FlightResult with mission/weather metadata so Discord doesn't
            # need a second prepare() call.
            result = FlightOutcome(
                result=FlightResult(
                    telemetry=tuple(points),
                    launch_request=launch_request,
                ),
                weather=prep.weather,
                mission_assignment=assignment,
                weather_impacts=prep.weather_impacts,
            )

            return result

        except Exception as e:
            logger.exception("Flight simulation failed")
            raise FlightServiceError(f"Flight simulation failed: {e}") from e


# Module-level singleton
flight_service = FlightService()