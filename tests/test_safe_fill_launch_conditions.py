"""Safe launch fills must respect the selected site's pressure and temperature."""

import pytest

from balloon_frontier.catalog import FillMode
from balloon_frontier.launch_result import LaunchRequest
from balloon_frontier.physics import (
    atmosphere_pressure,
    atmosphere_temperature,
    gas_volume,
)


def test_manual_mountain_fill_is_safe_at_launch_conditions():
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("none",),
        launch_site_id="mountain",
        fill_mode=FillMode.MANUAL,
        manual_gas_mass_kg=100.0,
    )

    launch_altitude_m = request.site.altitude_m
    launch_temperature_k = atmosphere_temperature(launch_altitude_m)
    launch_pressure_pa = atmosphere_pressure(launch_altitude_m)
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


def test_heated_gas_fill_is_safe_at_resolved_launch_temperature():
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("none",),
        launch_site_id="field",
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
