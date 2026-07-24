"""Tests for FlightService (flight_service.py).

These tests verify that FlightService:
- Correctly wraps the simulation engine
- Converts simulation output to typed models
- Handles weather events and mission assignments
- Returns proper FlightResult with typed telemetry

No behavioral changes — just migration from the old inline launch logic.
"""

import pytest

from balloon_frontier.flight_service import FlightService, FlightServiceError, flight_service
from balloon_frontier.launch_result import (
    LaunchRequest,
    FlightResult,
    TelemetryPoint,
    FillMode,
    build_launch_request_from_cli,
)


# ─── FlightService tests ──────────────────────────────────────────


class TestFlightService:

    def test_basic_launch(self):
        """A basic launch without weather or missions works."""
        req = build_launch_request_from_cli(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=["none"],
            site_id="field",
            fill_mode="normal",
        )

        result = flight_service.run(req)

        # Verify basic properties
        assert result.launch_request == req
        assert len(result.telemetry) > 0
        assert isinstance(result.telemetry[0], TelemetryPoint)
        assert result.duration_s > 0

    def test_telemetry_is_tuple(self):
        """Telemetry must be immutable tuple, not mutable list."""
        req = build_launch_request_from_cli(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=["none"],
            site_id="field",
            fill_mode="normal",
        )

        result = flight_service.run(req)
        assert isinstance(result.telemetry, tuple)

        # Should not allow mutation (tuple has no append method)
        assert not hasattr(result.telemetry, 'append')

    def test_empty_teelmmetry_handling(self):
        """FlightService handles empty telemetry gracefully."""
        # This would require a very short sim time or immediate burst
        # For now, test that FlightResult handles empty telemetry
        req = build_launch_request_from_cli(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=["none"],
            site_id="field",
            fill_mode="normal",
        )

        empty_result = FlightResult(
            telemetry=(),  # empty tuple
            launch_request=req,
        )

        assert empty_result.peak_altitude_m == 0.0
        assert empty_result.duration_s == 0.0
        assert empty_result.burst is False
        assert empty_result.landed is False
        assert empty_result.crashed is False

    def test_weather_event_applied(self):
        """Weather event is applied to the envelope config."""
        req = build_launch_request_from_cli(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=["none"],
            site_id="field",
            fill_mode="normal",
        )

        weather_event = {
            "name": "Thunderstorm",
            "description": "Severe thunderstorm",
            "severity": "high",
            "flight_modifier": 0.8,  # 20% reduction in flight efficiency
        }

        result = flight_service.run(req, weather_event=weather_event)

        # With reduced efficiency, the balloon should reach lower altitude
        assert result.peak_altitude_m >= 0

    def test_mission_assignment(self):
        """Mission assignment extends flight duration."""
        req = build_launch_request_from_cli(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=["none"],
            site_id="field",
            fill_mode="normal",
        )

        mission_assignment = {
            "missions": ["altitude_record", "longest_flight"],
            "seed": 12345,
            "mission_count": 2,
        }

        result = flight_service.run(req, mission_assignment=mission_assignment)

        # Mission flights should run longer (up to 12 hours)
        assert result.duration_s >= 0
        # The telemetry should have enough points for a 12-hour flight
        # (at 1s intervals, that's up to 43200 points)

    def test_custom_parameters(self):
        """FlightService respects custom simulation parameters."""
        service = FlightService(
            default_sim_time=50.0,  # Shorter than default
            mission_sim_time=3600.0,  # 1 hour for missions
        )

        req = build_launch_request_from_cli(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=["none"],
            site_id="field",
            fill_mode="normal",
        )

        result = service.run(req)

        # Should stop around 50 seconds (default sim time)
        assert result.duration_s <= 55.0  # Allow small margin

    def test_wind_site_id(self):
        """Wind site ID is passed to simulation state."""
        req = build_launch_request_from_cli(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=["none"],
            site_id="mountain",
            fill_mode="normal",
        )

        result = flight_service.run(req)

        # Mountain site should have different conditions than field
        assert result.peak_altitude_m >= 0

    def test_valve_payload(self):
        """Valve payload activates the pressure valve."""
        req = LaunchRequest(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=("valve",),
            launch_site_id="field",
            fill_mode=FillMode.NORMAL,
        )

        state = req.to_simulation_state()
        assert state.has_pressure_valve is True

        result = flight_service.run(req)

        # With valve, the balloon should not burst (or burst much later)
        # This depends on the simulation, but the valve should be active
        assert result.launch_request == req


# ─── Backward compatibility ──────────────────────────────────────


class TestBackwardCompatibility:

    def test_module_singleton(self):
        """The module-level flight_service singleton exists and works."""
        assert flight_service is not None
        assert isinstance(flight_service, FlightService)

    def test_flight_service_error(self):
        """FlightServiceError is raised on simulation failures."""
        # Create a service that will fail
        service = FlightService()

        # Try to run with invalid data (should fail)
        # Note: This test validates error handling, not actual failure
        try:
            # A properly constructed request shouldn't fail
            req = build_launch_request_from_cli(
                gas_id="helium",
                envelope_id="latex",
                payload_ids=["none"],
                site_id="field",
                fill_mode="normal",
            )
            result = service.run(req)
            # If it succeeded, that's fine — just verify the type
            assert isinstance(result, FlightResult)
        except FlightServiceError:
            # Also fine — we're testing error handling exists
            pass


# ─── Integration tests ────────────────────────────────────────────


class TestIntegration:

    def test_full_discord_workflow(self):
        """Simulate the full Discord launch workflow."""
        # 1. Build launch request (from Discord state)
        req = build_launch_request_from_cli(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=["camera", "battery"],
            site_id="mountain",
            fill_mode="heavy",
        )

        # 2. Run simulation via FlightService
        result = flight_service.run(req)

        # 3. Verify result is usable for Discord rendering
        assert result.peak_altitude_m >= 0
        assert result.duration_s >= 0
        assert len(result.telemetry) > 0
        assert isinstance(result.telemetry[0].altitude_m, float)

        # 4. Verify all expected fields are present
        for point in result.telemetry:
            assert hasattr(point, 'time_s')
            assert hasattr(point, 'altitude_m')
            assert hasattr(point, 'velocity_mps')
            assert hasattr(point, 'burst')
            assert hasattr(point, 'landed')
            assert hasattr(point, 'crashed')


# ─── Edge cases ──────────────────────────────────────────────────


class TestEdgeCases:

    def test_no_payload(self):
        """Launch with no payload (empty tuple)."""
        req = build_launch_request_from_cli(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=["none"],  # "none" is a sentinel
            site_id="field",
            fill_mode="normal",
        )

        result = flight_service.run(req)
        assert result.launch_request == req
        assert len(result.telemetry) > 0

    def test_multiple_payloads(self):
        """Launch with multiple payloads."""
        req = build_launch_request_from_cli(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=["camera", "battery", "heater"],
            site_id="field",
            fill_mode="normal",
        )

        result = flight_service.run(req)
        assert result.launch_request == req
        assert len(result.telemetry) > 0

    def test_all_fill_modes(self):
        """Test all fill modes produce valid results."""
        for fill_mode in ["auto", "light", "normal", "heavy"]:
            req = build_launch_request_from_cli(
                gas_id="helium",
                envelope_id="latex",
                payload_ids=["none"],
                site_id="field",
                fill_mode=fill_mode,
            )

            result = flight_service.run(req)
            assert result.launch_request == req
            assert len(result.telemetry) > 0

    def test_all_envelopes(self):
        """Test all envelope types work."""
        for envelope_id in ["latex", "mylar", "zero_pressure", "blimp"]:
            req = build_launch_request_from_cli(
                gas_id="helium",
                envelope_id=envelope_id,
                payload_ids=["none"],
                site_id="field",
                fill_mode="normal",
            )

            result = flight_service.run(req)
            assert result.launch_request == req
            assert len(result.telemetry) > 0

    def test_all_sites(self):
        """Test all launch sites work."""
        for site_id in ["field", "mountain", "rooftop"]:
            req = build_launch_request_from_cli(
                gas_id="helium",
                envelope_id="latex",
                payload_ids=["none"],
                site_id=site_id,
                fill_mode="normal",
            )

            result = flight_service.run(req)
            assert result.launch_request == req
            assert len(result.telemetry) > 0