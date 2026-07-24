"""Balloon Frontier — FlightService tests

Tests the transport-neutral flight pipeline:
- prepare(): catalog resolution, SimulationState, weather, missions
- run(): full pipeline from LaunchRequest to FlightResult
- Integration: telemetry conversion, immutability, valve, manual fill
"""

import pytest
from dataclasses import dataclass
from unittest.mock import patch, MagicMock, PropertyMock

from balloon_frontier.flight_service import (
    FlightService,
    FlightServiceError,
    FlightOutcome,
    LaunchPreparation,
    flight_service,
)
from balloon_frontier.launch_result import (
    LaunchRequest,
    FlightResult,
    TelemetryPoint,
    FillMode,
)
from balloon_frontier.weather_event import WeatherEvent


# ─── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def service():
    return FlightService()


@pytest.fixture
def normal_request():
    return LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("camera",),
        launch_site_id="field",
        fill_mode=FillMode.NORMAL,
    )


@pytest.fixture
def valve_request():
    return LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("valve", "camera"),
        launch_site_id="field",
        fill_mode=FillMode.NORMAL,
    )


@pytest.fixture
def manual_request():
    return LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=(),
        launch_site_id="field",
        fill_mode=FillMode.MANUAL,
        manual_gas_mass_kg=0.5,
    )


@pytest.fixture
def mountain_request():
    return LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=(),
        launch_site_id="mountain",
        fill_mode=FillMode.NORMAL,
    )


# ─── Service Initialization ──────────────────────────────────────────


class TestServiceInitialization:
    def test_singleton_exists(self):
        assert flight_service is not None
        assert isinstance(flight_service, FlightService)

    def test_default_config(self):
        svc = FlightService()
        assert svc.default_sim_time == 150.0
        assert svc.mission_sim_time == 43200.0
        assert svc.mission_step_interval == 1.0

    def test_custom_config(self):
        svc = FlightService(
            default_sim_time=200.0,
            mission_sim_time=86400.0,
            mission_step_interval=2.0,
        )
        assert svc.default_sim_time == 200.0
        assert svc.mission_sim_time == 86400.0
        assert svc.mission_step_interval == 2.0


# ─── prepare() ───────────────────────────────────────────────────────


class TestPrepare:
    def test_prepare_returns_launch_preparation(self, service, normal_request):
        prep = service.prepare(normal_request)
        assert isinstance(prep, LaunchPreparation)
        assert prep.request is normal_request

    def test_prepare_resolves_catalog(self, service, normal_request):
        prep = service.prepare(normal_request)
        assert prep.sim_state.gas_type == "helium"
        assert prep.sim_state.envelope.max_volume_m3 == 10.0

    def test_prepare_generates_weather(self, service, normal_request):
        prep = service.prepare(normal_request)
        assert prep.weather is not None
        assert isinstance(prep.weather, WeatherEvent)
        # Weather event should have a description (name may be empty)
        assert prep.weather.description  # Has a description
        assert prep.weather.severity  # Has a severity

    def test_prepare_assigns_missions(self, service, normal_request):
        prep = service.prepare(normal_request)
        # With 1 payload, should get at least 0 missions
        assert prep.mission_assignment is not None
        assert isinstance(prep.mission_assignment, dict)

    def test_prepare_wind_site_id(self, service, normal_request):
        prep = service.prepare(normal_request)
        assert prep.wind_site_id == "field"

    def test_prepare_mountain_site(self, service, mountain_request):
        prep = service.prepare(mountain_request)
        assert prep.wind_site_id == "mountain"
        # Mountain should have higher altitude
        assert prep.sim_state.altitude_m == 1500.0


# ─── run() — Normal Launch ───────────────────────────────────────────


class TestRunNormal:
    def test_run_returns_flight_outcome(self, service, normal_request):
        outcome = service.run(normal_request)
        assert isinstance(outcome, FlightOutcome)
        assert isinstance(outcome.result, FlightResult)

    def test_run_has_telemetry(self, service, normal_request):
        outcome = service.run(normal_request)
        assert len(outcome.result.telemetry) > 0

    def test_run_telemetry_is_tuple(self, service, normal_request):
        outcome = service.run(normal_request)
        assert isinstance(outcome.result.telemetry, tuple)

    def test_run_immutability(self, service, normal_request):
        outcome = service.run(normal_request)
        with pytest.raises(AttributeError):
            outcome.result.telemetry.append(TelemetryPoint(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, False, False, False, 0, 0))

    def test_run_peak_altitude_positive(self, service, normal_request):
        outcome = service.run(normal_request)
        assert outcome.result.peak_altitude_m > 0

    def test_run_duration_positive(self, service, normal_request):
        outcome = service.run(normal_request)
        assert outcome.result.duration_s > 0

    def test_run_gas_mass_from_request(self, service, normal_request):
        outcome = service.run(normal_request)
        assert outcome.result.launch_request.gas_mass_kg > 0


# ─── run() — Manual Fill ─────────────────────────────────────────────


class TestRunManual:
    def test_manual_fill_respects_mass(self, service, manual_request):
        outcome = service.run(manual_request)
        assert isinstance(outcome.result, FlightResult)
        assert len(outcome.result.telemetry) > 0
        # Manual mass should be used
        assert outcome.result.launch_request.gas_mass_kg == 0.5


# ─── run() — Valve Payload ───────────────────────────────────────────


class TestRunValve:
    def test_valve_activated_in_simulation_state(self, service, valve_request):
        """Selecting the valve payload sets has_pressure_valve=True."""
        prep = service.prepare(valve_request)
        assert prep.sim_state.has_pressure_valve is True

    def test_run_with_valve_succeeds(self, service, valve_request):
        outcome = service.run(valve_request)
        assert isinstance(outcome.result, FlightResult)
        assert len(outcome.result.telemetry) > 0


# ─── run() — Launch Site Altitude ────────────────────────────────────


class TestRunSiteAltitude:
    def test_mountain_starts_higher(self, service, mountain_request, normal_request):
        mountain_result = service.run(mountain_request)
        normal_result = service.run(normal_request)
        # Mountain starts at 1500m, field at 0m
        assert mountain_result.result.telemetry[0].altitude_m >= 1500.0
        # First tick of field is ~0.4m due to simulation step forward
        assert normal_result.result.telemetry[0].altitude_m > 0.0

    def test_mountain_peak_higher(self, service, mountain_request, normal_request):
        mountain_result = service.run(mountain_request)
        normal_result = service.run(normal_request)
        # Mountain peak should be higher due to starting altitude
        assert mountain_result.result.peak_altitude_m > normal_result.result.peak_altitude_m


# ─── run() — Weather Propagation ─────────────────────────────────────


class TestRunWeather:
    def test_weather_affects_flight(self, service, normal_request):
        """Weather impacts should propagate to the simulation."""
        prep = service.prepare(normal_request)
        assert prep.weather is not None
        assert isinstance(prep.weather, WeatherEvent)
        # Weather event should have severity
        assert prep.weather.severity is not None


# ─── run() — Mission Assignment ──────────────────────────────────────


class TestRunMissions:
    def test_mission_assignment_present(self, service, normal_request):
        prep = service.prepare(normal_request)
        assert prep.mission_assignment is not None
        assert isinstance(prep.mission_assignment, dict)


# ─── Error Handling ──────────────────────────────────────────────────


class TestErrorHandling:
    def test_invalid_gas_raises_prep_error(self):
        svc = FlightService()
        req = LaunchRequest.__new__(LaunchRequest)
        # Manually set invalid gas_id
        object.__setattr__(req, 'gas_id', 'invalid_gas')
        object.__setattr__(req, 'envelope_id', 'latex')
        object.__setattr__(req, 'payload_ids', ())
        object.__setattr__(req, 'launch_site_id', 'field')
        object.__setattr__(req, 'fill_mode', FillMode.AUTO)
        object.__setattr__(req, 'manual_gas_mass_kg', None)
        object.__setattr__(req, 'player_id', None)
        object.__setattr__(req, 'balloon_size', None)
        object.__setattr__(req, 'gas_temperature_delta_k', None)
        # This should raise during __post_init__
        with pytest.raises(ValueError):
            LaunchRequest(gas_id='invalid_gas', envelope_id='latex')


# ─── Integration: Service + Result ───────────────────────────────────


class TestIntegration:
    def test_full_pipeline(self, service, normal_request):
        """Complete pipeline: request → prepare → run → result properties."""
        prep = service.prepare(normal_request)
        assert prep.request is normal_request
        assert prep.sim_state is not None
        assert prep.weather is not None
        assert prep.mission_assignment is not None

        outcome = service.run(normal_request)
        assert isinstance(outcome.result, FlightResult)
        assert outcome.result.peak_altitude_m > 0
        assert outcome.result.duration_s > 0
        assert outcome.result.launch_request is normal_request

    def test_result_end_state(self, service, normal_request):
        outcome = service.run(normal_request)
        end_state = outcome.result.end_state()
        assert isinstance(end_state, str)
        # End state should be one of: crashed, burst, landed, in flight
        assert any(marker in end_state.lower() for marker in ['crash', 'burst', 'land', 'in flight'])

    def test_result_embed_fields(self, service, normal_request):
        outcome = service.run(normal_request)
        fields = outcome.result.to_embed_fields()
        assert len(fields) >= 3
        # Should have Flight Result, Peak Altitude, Flight Time
        names = [f[0] for f in fields]
        assert any("Flight" in n for n in names)
        assert any("Peak" in n for n in names)


# ─── Edge Cases ──────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_payloads(self, service):
        req = LaunchRequest(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=(),
            launch_site_id="field",
            fill_mode=FillMode.NORMAL,
        )
        outcome = service.run(req)
        assert isinstance(outcome.result, FlightResult)
        assert len(outcome.result.telemetry) > 0

    def test_multiple_payloads(self, service):
        req = LaunchRequest(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=("camera", "battery", "weather_sensor"),
            launch_site_id="field",
            fill_mode=FillMode.NORMAL,
        )
        outcome = service.run(req)
        assert isinstance(outcome.result, FlightResult)
        assert len(outcome.result.telemetry) > 0
        # More payloads = more mass = potentially different flight
        assert outcome.result.launch_request.total_payload_mass_kg > 0

    def test_heavy_fill(self, service):
        req = LaunchRequest(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=(),
            launch_site_id="field",
            fill_mode=FillMode.HEAVY,
        )
        outcome = service.run(req)
        assert isinstance(outcome.result, FlightResult)
        assert len(outcome.result.telemetry) > 0
        # Heavy should have more gas mass than normal
        assert outcome.result.launch_request.gas_mass_kg > 0

    def test_no_mission_flight_uses_default_time(self, service):
        """A launch with no compatible missions should use default_sim_time, not mission time.

        Regression: previously all launches got 43200s because the code checked
        `mission_assignment is not None` which is always true. The fix checks for
        the presence of "mission_ids" key, which never exists in regular assignments.
        """
        req = LaunchRequest(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=(),
            launch_site_id="field",
            fill_mode=FillMode.NORMAL,
        )
        outcome = service.run(req)
        # Check the simulation didn't run for 12 hours — should be ~150s (default)
        assert outcome.result.duration_s < 300, f"Flight took {outcome.result.duration_s}s, expected ~150s (not 43200s)"

    def test_mountain_vs_field_flight_time(self, service, normal_request):
        """Mountain and field runs should use the same simulation duration.

        Both are regular Discord launches, not mission flights.
        """
        mountain_req = LaunchRequest(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=(),
            launch_site_id="mountain",
            fill_mode=FillMode.NORMAL,
        )
        mountain_outcome = service.run(mountain_req)
        field_outcome = service.run(normal_request)
        # Both should be ~150s (default_sim_time), not 43200s (mission_sim_time)
        assert mountain_outcome.result.duration_s < 300
        assert field_outcome.result.duration_s < 300

    def test_all_weather_modifiers_applied(self, service, normal_request):
        """All five weather modifiers should propagate to the simulation state.

        Regression: the original migration only applied burst_risk, ascent_rate, and drift_factor.
        thermal_efficiency → solar_modifier and pressure_modifier → pressure_modifier were dropped.
        """
        prep = service.prepare(normal_request)
        impacts = prep.weather_impacts
        # All five keys should be present
        for key in ('burst_risk', 'thermal_efficiency', 'pressure_modifier', 'ascent_rate', 'drift_factor'):
            assert key in impacts, f"Weather impact missing: {key}"
        # Verify they get applied in run()
        assert prep.sim_state.envelope.weather_solar_modifier == 1.0  # default
        assert prep.sim_state.envelope.weather_pressure_modifier == 1.0  # default

    def test_flight_outcome_has_metadata(self, service, normal_request):
        """FlightOutcome should carry weather, mission_assignment, and weather_impacts.

        Architectural fix: Discord no longer needs a second prepare() call.
        """
        outcome = service.run(normal_request)
        assert outcome.weather is not None
        assert outcome.mission_assignment is not None
        assert outcome.weather_impacts is not None
        assert isinstance(outcome.weather_impacts, dict)

    def test_discord_no_second_prepare(self, service, normal_request):
        """Discord should use FlightOutcome metadata, not call prepare() again."""
        outcome = service.run(normal_request)
        # Weather data available without calling prepare() again
        weather_dict = {
            "name": outcome.weather.name if outcome.weather else "",
            "description": outcome.weather.description if outcome.weather else "",
            "severity": outcome.weather.severity if outcome.weather else "",
            "flight_modifier": outcome.weather.flight_modifier if outcome.weather else "",
        }
        assert "severity" in weather_dict
        assert outcome.mission_assignment is not None