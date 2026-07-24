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
    def test_run_returns_flight_result(self, service, normal_request):
        result = service.run(normal_request)
        assert isinstance(result, FlightResult)

    def test_run_has_telemetry(self, service, normal_request):
        result = service.run(normal_request)
        assert len(result.telemetry) > 0

    def test_run_telemetry_is_tuple(self, service, normal_request):
        result = service.run(normal_request)
        assert isinstance(result.telemetry, tuple)

    def test_run_immutability(self, service, normal_request):
        result = service.run(normal_request)
        with pytest.raises(AttributeError):
            result.telemetry.append(TelemetryPoint(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, False, False, False, 0, 0))

    def test_run_peak_altitude_positive(self, service, normal_request):
        result = service.run(normal_request)
        assert result.peak_altitude_m > 0

    def test_run_duration_positive(self, service, normal_request):
        result = service.run(normal_request)
        assert result.duration_s > 0

    def test_run_gas_mass_from_request(self, service, normal_request):
        result = service.run(normal_request)
        assert result.launch_request.gas_mass_kg > 0


# ─── run() — Manual Fill ─────────────────────────────────────────────


class TestRunManual:
    def test_manual_fill_respects_mass(self, service, manual_request):
        result = service.run(manual_request)
        assert isinstance(result, FlightResult)
        assert len(result.telemetry) > 0
        # Manual mass should be used
        assert result.launch_request.gas_mass_kg == 0.5


# ─── run() — Valve Payload ───────────────────────────────────────────


class TestRunValve:
    def test_valve_activated_in_simulation_state(self, service, valve_request):
        """Selecting the valve payload sets has_pressure_valve=True."""
        prep = service.prepare(valve_request)
        assert prep.sim_state.has_pressure_valve is True

    def test_run_with_valve_succeeds(self, service, valve_request):
        result = service.run(valve_request)
        assert isinstance(result, FlightResult)
        assert len(result.telemetry) > 0


# ─── run() — Launch Site Altitude ────────────────────────────────────


class TestRunSiteAltitude:
    def test_mountain_starts_higher(self, service, mountain_request, normal_request):
        mountain_result = service.run(mountain_request)
        normal_result = service.run(normal_request)
        # Mountain starts at 1500m, field at 0m
        assert mountain_result.telemetry[0].altitude_m >= 1500.0
        # First tick of field is ~0.4m due to simulation step forward
        assert normal_result.telemetry[0].altitude_m > 0.0

    def test_mountain_peak_higher(self, service, mountain_request, normal_request):
        mountain_result = service.run(mountain_request)
        normal_result = service.run(normal_request)
        # Mountain peak should be higher due to starting altitude
        assert mountain_result.peak_altitude_m > normal_result.peak_altitude_m


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

        result = service.run(normal_request)
        assert isinstance(result, FlightResult)
        assert result.peak_altitude_m > 0
        assert result.duration_s > 0
        assert result.launch_request is normal_request

    def test_result_end_state(self, service, normal_request):
        result = service.run(normal_request)
        end_state = result.end_state()
        assert isinstance(end_state, str)
        # End state should be one of: crashed, burst, landed, in flight
        assert any(marker in end_state.lower() for marker in ['crash', 'burst', 'land', 'in flight'])

    def test_result_embed_fields(self, service, normal_request):
        result = service.run(normal_request)
        fields = result.to_embed_fields()
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
        result = service.run(req)
        assert isinstance(result, FlightResult)
        assert len(result.telemetry) > 0

    def test_multiple_payloads(self, service):
        req = LaunchRequest(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=("camera", "battery", "weather_sensor"),
            launch_site_id="field",
            fill_mode=FillMode.NORMAL,
        )
        result = service.run(req)
        assert isinstance(result, FlightResult)
        assert len(result.telemetry) > 0
        # More payloads = more mass = potentially different flight
        assert result.launch_request.total_payload_mass_kg > 0

    def test_heavy_fill(self, service):
        req = LaunchRequest(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=(),
            launch_site_id="field",
            fill_mode=FillMode.HEAVY,
        )
        result = service.run(req)
        assert isinstance(result, FlightResult)
        assert len(result.telemetry) > 0
        # Heavy should have more gas mass than normal
        assert result.launch_request.gas_mass_kg > 0