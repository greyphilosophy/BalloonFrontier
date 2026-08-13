"""Launch fills must be safe and pressure valves must remain optional equipment."""

import pytest

from balloon_frontier.balloon_cluster import ClusteredLaunchRequest
from balloon_frontier.career_prologue import (
    FIRST_FLIGHT_OPTION_KEYS,
    FIRST_FLIGHT_REQUIRED_PAYLOADS,
)
from balloon_frontier.catalog import CATALOG, FillMode
from balloon_frontier.launch_result import LaunchRequest
from balloon_frontier.physics import atmosphere_pressure, gas_density, gas_volume
from balloon_frontier.simulation import simulation_step


def _gas_density(request: LaunchRequest) -> float:
    return gas_density(
        request.gas.id,
        288.15,
        atmosphere_pressure(0.0),
    )


def _expected_nominal_mass(request: LaunchRequest) -> float:
    return (
        _gas_density(request)
        * request.envelope.max_volume_m3
        * request.fill_mode.get_multiplier()
    )


def test_heavy_latex_fill_uses_nominal_volume():
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("camera",),
        launch_site_id="field",
        fill_mode=FillMode.HEAVY,
    )

    assert request.gas_mass_kg == pytest.approx(_expected_nominal_mass(request))

    initial_volume = gas_volume(
        request.gas_mass_kg,
        request.gas.id,
        288.15,
        atmosphere_pressure(0.0),
    )
    assert initial_volume == pytest.approx(
        request.envelope.max_volume_m3 * FillMode.HEAVY.get_multiplier()
    )
    assert initial_volume < request.envelope.burst_volume_m3


def test_manual_fill_is_clamped_below_burst_safe_capacity():
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("camera",),
        launch_site_id="field",
        fill_mode=FillMode.MANUAL,
        manual_gas_mass_kg=100.0,
    )

    safe_volume = (
        request.envelope.burst_volume_m3
        * request.envelope.safe_fill_fraction
    )
    safe_mass = _gas_density(request) * safe_volume
    actual_volume = gas_volume(
        request.gas_mass_kg,
        request.gas.id,
        288.15,
        atmosphere_pressure(0.0),
    )

    assert request.gas_mass_kg == pytest.approx(safe_mass)
    assert actual_volume == pytest.approx(safe_volume)
    assert actual_volume < request.envelope.burst_volume_m3


def test_manual_cluster_fill_uses_total_cluster_safety_capacity():
    request = ClusteredLaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("camera",),
        launch_site_id="field",
        fill_mode=FillMode.MANUAL,
        manual_gas_mass_kg=100.0,
        balloon_count=3,
    )

    per_balloon_safe_volume = (
        request.envelope.burst_volume_m3
        * request.envelope.safe_fill_fraction
    )
    expected_total_mass = (
        _gas_density(request) * per_balloon_safe_volume * request.balloon_count
    )

    assert request.gas_mass_kg == pytest.approx(expected_total_mass)

    state = request.to_simulation_state()
    actual_total_volume = gas_volume(
        state.gas_mass_kg,
        state.gas_type,
        288.15,
        atmosphere_pressure(0.0),
    )
    assert actual_total_volume == pytest.approx(
        per_balloon_safe_volume * request.balloon_count
    )
    assert actual_total_volume < (
        request.envelope.burst_volume_m3 * request.balloon_count
    )


def test_manual_cluster_scales_cli_manufacturer_limit():
    request = ClusteredLaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("none",),
        launch_site_id="field",
        fill_mode=FillMode.MANUAL,
        manual_gas_mass_kg=100.0,
        balloon_size="s36",
        balloon_count=3,
    )

    assert request.balloon is not None
    per_balloon_max_kg = request.balloon.fill_range_g[1] / 1000.0
    safe_total_kg = (
        _gas_density(request)
        * request.balloon.max_volume_m3
        * request.balloon.burst_stretch_ratio
        * request.envelope.safe_fill_fraction
        * request.balloon_count
    )
    expected_total_kg = min(per_balloon_max_kg * 3, safe_total_kg)

    assert request.gas_mass_kg == pytest.approx(expected_total_kg)


def test_camera_does_not_include_a_pressure_valve():
    camera = CATALOG.payload("camera")
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("camera",),
        launch_site_id="field",
        fill_mode=FillMode.HEAVY,
    )
    state = request.to_simulation_state()

    assert camera.has_valve is False
    assert state.has_pressure_valve is False
    assert request.total_payload_mass_kg == pytest.approx(camera.mass_kg)


def test_pressure_valve_adds_its_own_mass_and_cost():
    camera = CATALOG.payload("camera")
    valve = CATALOG.payload("valve")
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("camera", "valve"),
        launch_site_id="field",
        fill_mode=FillMode.HEAVY,
    )
    state = request.to_simulation_state()

    assert valve.has_valve is True
    assert valve.mass_kg == pytest.approx(0.3)
    assert valve.cost == 250
    assert state.has_pressure_valve is True
    assert request.total_payload_mass_kg == pytest.approx(
        camera.mass_kg + valve.mass_kg
    )


def test_first_flight_menu_exposes_only_optional_foundational_experiments():
    payloads = FIRST_FLIGHT_OPTION_KEYS[3]

    assert FIRST_FLIGHT_REQUIRED_PAYLOADS == ("camera", "quadcopter")
    assert payloads == (
        "parachute",
        "candle_heater",
        "electric_heater",
        "none",
    )
    assert "camera" not in payloads
    assert "quadcopter" not in payloads
    assert "valve" not in payloads
    assert "heater" not in payloads


def test_heavy_latex_camera_lifts_without_automatic_venting():
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("camera",),
        launch_site_id="field",
        fill_mode=FillMode.HEAVY,
    )
    state = request.to_simulation_state()
    initial_mass = state.gas_mass_kg

    telemetry = simulation_step(state, dt=0.1)

    assert state.has_pressure_valve is False
    assert telemetry["velocity_mps"] > 0.0
    assert telemetry["altitude_m"] > 0.0
    assert telemetry["gas_mass_kg"] == pytest.approx(initial_mass, rel=0.001)
    assert telemetry["landed"] is False
    assert telemetry["crashed"] is False


def test_cluster_multiplies_corrected_per_balloon_fill():
    request = ClusteredLaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("camera",),
        launch_site_id="field",
        fill_mode=FillMode.HEAVY,
        balloon_count=3,
    )

    per_balloon = _expected_nominal_mass(request)
    assert request.gas_mass_kg == pytest.approx(per_balloon * 3)

    state = request.to_simulation_state()
    assert state.envelope.max_volume_m3 == pytest.approx(
        request.envelope.max_volume_m3 * 3
    )
    assert state.gas_mass_kg == pytest.approx(per_balloon * 3)
