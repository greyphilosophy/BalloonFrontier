"""Launch fills must be safe and pressure valves must remain optional equipment."""

import pytest

from balloon_frontier.balloon_cluster import ClusteredLaunchRequest
from balloon_frontier.catalog import CATALOG, FillMode
from balloon_frontier.launch_result import LaunchRequest
from balloon_frontier.physics import atmosphere_pressure, gas_density, gas_volume
from balloon_frontier.simulation import simulation_step
from balloon_frontier.tutorial_catalog import (
    QUADCOPTER,
    ensure_discord_tutorial_options,
)


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
        payload_ids=("quadcopter",),
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
        payload_ids=("quadcopter",),
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


def test_quadcopter_does_not_include_a_pressure_valve():
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("quadcopter",),
        launch_site_id="field",
        fill_mode=FillMode.HEAVY,
    )
    state = request.to_simulation_state()

    assert QUADCOPTER.has_valve is False
    assert state.has_pressure_valve is False
    assert request.total_payload_mass_kg == pytest.approx(QUADCOPTER.mass_kg)


def test_pressure_valve_adds_its_own_mass_and_cost():
    valve = CATALOG.payload("valve")
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("quadcopter", "valve"),
        launch_site_id="field",
        fill_mode=FillMode.HEAVY,
    )
    state = request.to_simulation_state()

    assert valve.has_valve is True
    assert valve.mass_kg > 0
    assert valve.cost > 0
    assert state.has_pressure_valve is True
    assert request.total_payload_mass_kg == pytest.approx(
        QUADCOPTER.mass_kg + valve.mass_kg
    )


def test_tutorial_exposes_valve_as_an_independent_payload():
    ensure_discord_tutorial_options()
    from balloon_frontier.tutorial import TUTORIAL_OPTION_KEYS

    assert TUTORIAL_OPTION_KEYS[3] == ("quadcopter", "valve", "none")


def test_heavy_latex_quadcopter_lifts_without_automatic_venting():
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("quadcopter",),
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
        payload_ids=("quadcopter",),
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
