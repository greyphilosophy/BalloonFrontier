"""The offered First Flight assist setup must genuinely use powered vertical control."""

from balloon_frontier.aerostat import configured_simulation_state
from balloon_frontier.catalog import CATALOG, FillMode
from balloon_frontier.launch_result import LaunchRequest
from balloon_frontier.physics import atmosphere_density, atmosphere_pressure, gas_density
from balloon_frontier.power import powered_assist_gas_mass_kg
from balloon_frontier.powered_simulation import run_powered_simulation


def test_first_flight_powered_assist_requires_quadcopter_vertical_lift():
    payload_ids = ("camera", "quadcopter", "battery")
    envelope = CATALOG.envelope("latex")
    payload_mass_kg = sum(CATALOG.payload(pid).mass_kg for pid in payload_ids)
    gas_temp_k = CATALOG.site("field").gas_temperature_k or 288.15
    pressure_pa = atmosphere_pressure(0.0)
    helium_density = gas_density("helium", gas_temp_k, pressure_pa)

    assist_mass_kg = powered_assist_gas_mass_kg(
        non_gas_mass_kg=envelope.mass_kg + payload_mass_kg,
        ambient_density_kg_m3=atmosphere_density(0.0),
        lifting_gas_density_kg_m3=helium_density,
        max_volume_m3=envelope.max_volume_m3,
    )
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=payload_ids,
        launch_site_id="field",
        fill_mode=FillMode.MANUAL,
        manual_gas_mass_kg=assist_mass_kg,
    )
    state = configured_simulation_state(request, request.to_simulation_state())
    state.wind_enabled = False

    result = run_powered_simulation(
        state,
        payload_ids=payload_ids,
        dt=0.1,
        total_time_s=2.0,
    )

    assert result.telemetry
    assert max(tick["vertical_control_force_N"] for tick in result.telemetry) > 0.0
    assert max(tick["altitude_m"] for tick in result.telemetry) > 0.0
    assert result.battery_remaining_wh < result.battery_capacity_wh
