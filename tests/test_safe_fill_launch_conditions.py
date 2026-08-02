"""Safe launch fills must respect the selected site's pressure and temperature."""

import pytest

from balloon_frontier.catalog import FillMode
from balloon_frontier.launch_result import LaunchRequest
from balloon_frontier.physics import (
    atmosphere_pressure,
    atmosphere_temperature,
    gas_volume,
)


def _site_launch_temperature(request: LaunchRequest) -> float:
    ambient_k = atmosphere_temperature(request.site.altitude_m)
    if request.gas_temperature_delta_k is not None:
        return ambient_k + request.gas_temperature_delta_k
    if request.site.gas_temperature_k is not None:
        return request.site.gas_temperature_k
    return ambient_k + request.site.temperature_offset_k


def test_manual_mountain_fill_is_safe_at_launch_conditions():
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("none",),
        launch_site_id="mountain",
        fill_mode=FillMode.MANUAL,
        manual_gas_mass_kg=100.0,
    )

    launch_temperature_k = _site_launch_temperature(request)
    launch_pressure_pa = atmosphere_pressure(request.site.altitude_m)
    launch_volume_m3 = gas_volume(
        request.gas_mass_kg,
        request.gas.id,
        launch_temperature_k,
        launch_pressure_pa,
    )
    safe_volume_m3 = (
        request.envelope.burst_volume_m3
        * request.envelope.safe_fill_fraction
    )

    assert launch_volume_m3 == pytest.approx(safe_volume_m3)
    assert launch_volume_m3 < request.envelope.burst_volume_m3

    state = request.to_simulation_state()
    assert state.gas_temperature_k == pytest.approx(launch_temperature_k)


def test_site_temperature_drives_preset_mass_and_simulation_state():
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("none",),
        launch_site_id="mountain",
        fill_mode=FillMode.HEAVY,
    )

    launch_temperature_k = _site_launch_temperature(request)
    launch_volume_m3 = gas_volume(
        request.gas_mass_kg,
        request.gas.id,
        launch_temperature_k,
        atmosphere_pressure(request.site.altitude_m),
    )

    assert launch_volume_m3 == pytest.approx(
        request.envelope.max_volume_m3 * FillMode.HEAVY.get_multiplier()
    )
    assert request.to_simulation_state().gas_temperature_k == pytest.approx(
        launch_temperature_k
    )


def test_explicit_temperature_offset_overrides_site_default():
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("none",),
        launch_site_id="mountain",
        fill_mode=FillMode.MANUAL,
        manual_gas_mass_kg=100.0,
        gas_temperature_delta_k=40.0,
    )

    launch_temperature_k = (
        atmosphere_temperature(request.site.altitude_m)
        + request.gas_temperature_delta_k
    )
    launch_volume_m3 = gas_volume(
        request.gas_mass_kg,
        request.gas.id,
        launch_temperature_k,
        atmosphere_pressure(request.site.altitude_m),
    )
    safe_volume_m3 = (
        request.envelope.burst_volume_m3
        * request.envelope.safe_fill_fraction
    )

    assert launch_volume_m3 == pytest.approx(safe_volume_m3)
    assert launch_volume_m3 < request.envelope.burst_volume_m3
    assert request.to_simulation_state().gas_temperature_k == pytest.approx(
        launch_temperature_k
    )
