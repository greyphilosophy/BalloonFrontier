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
result = flight_service.run(req, weather_event=None, mission_assignment=None)

# Access the result
print(f"Peak altitude: {result.peak_altitude_m} m")
print(f"Burst: {result.burst}")
print(f"Telemetry points: {len(result.telemetry)}")
```
"""

from __future__ import annotations

from typing import Optional

from balloon_frontier.launch_result import (
    LaunchRequest,
    FlightResult,
    TelemetryPoint,
    telemetry_list_to_points,
)
from balloon_frontier.simulation import (
    run_simulation as run_full_simulation,
)


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

    def run(
        self,
        launch_request: LaunchRequest,
        weather_event: Optional[dict] = None,
        mission_assignment: Optional[dict] = None,
        wind_site_id: str = "field",
    ) -> FlightResult:
        """Execute the full flight pipeline.

        Args:
            launch_request: The player's launch configuration.
            weather_event: Optional weather dict (name, description, severity,
                flight_modifier). If provided, its impacts are applied to the
                envelope config before simulation.
            mission_assignment: Optional mission assignment dict. If provided,
                the flight runs for the full mission duration.
            wind_site_id: Site wind profile identifier.

        Returns:
            FlightResult with complete telemetry and metadata.

        Raises:
            FlightServiceError: If simulation fails.
        """
        try:
            # Build simulation state from the launch request
            sim_state = launch_request.to_simulation_state()

            # Apply weather impacts if present
            if weather_event:
                # Weather impacts are applied via the envelope config
                # (handled by the simulation engine)
                sim_state.envelope.weather_burst_risk_modifier = weather_event.get(
                    "flight_modifier", 1.0
                )

            # Determine simulation duration
            max_time = self.mission_sim_time if mission_assignment else self.default_sim_time
            max_steps = int(max_time / 0.1)

            # Run simulation
            step_interval = self.mission_step_interval if mission_assignment else None
            tel_full = run_full_simulation(
                sim_state,
                dt=0.1,
                total_time_s=max_time,
                max_steps=max_steps,
                step_interval=step_interval,
            )

            if not tel_full:
                # Empty telemetry — return result with zeroed values
                result = FlightResult(
                    telemetry=(),
                    launch_request=launch_request,
                )
                return result

            # Convert raw telemetry dicts to TelemetryPoint objects
            points = telemetry_list_to_points(tel_full)

            # Build FlightResult (telemetry is converted to tuple for immutability)
            result = FlightResult(
                telemetry=tuple(points),
                launch_request=launch_request,
            )

            return result

        except Exception as e:
            raise FlightServiceError(f"Flight simulation failed: {e}") from e


# Module-level singleton
flight_service = FlightService()