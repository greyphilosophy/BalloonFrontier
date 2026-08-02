"""Preset fills must use nominal launch volume rather than burst capacity."""

import pytest

from balloon_frontier.balloon_cluster import ClusteredLaunchRequest
from balloon_frontier.catalog import FillMode
from balloon_frontier.launch_result import LaunchRequest
from balloon_frontier.physics import atmosphere_pressure, gas_density, gas_volume
from balloon_frontier.simulation import simulation_step


def _expected_nominal_mass(request: LaunchRequest) -> float:
    density = gas_density(
        request.gas.id,
        288.15,
        atmosphere_pressure(0.0),
    )
    return density * request.envelope.max_volume_m3 * request.fill_mode.get_multiplier()


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


def test_heavy_latex_quadcopter_lifts_instead_of_immediately_venting():
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
