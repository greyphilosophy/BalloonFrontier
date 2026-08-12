"""Coverage edges for the unified aerostat functional core."""

from balloon_frontier.aerostat import (
    configured_simulation_state,
    fill_mass_for_configuration,
    horizontal_control_accel_mps2,
    register_aerostat_catalog_extensions,
)
from balloon_frontier.catalog import CATALOG, FillMode
from balloon_frontier.launch_result import LaunchRequest


def test_fill_resolution_handles_balloon_override_and_temperature_delta():
    mass = fill_mass_for_configuration(
        gas_id="helium",
        envelope_id="latex",
        launch_site_id="field",
        fill_mode=FillMode.NORMAL,
        balloon_size="s36",
        gas_temperature_delta_k=15.0,
    )

    assert mass > 0.0


def test_quadcopter_is_shared_control_equipment_and_station_keeps():
    assert horizontal_control_accel_mps2(()) == 0.0
    assert horizontal_control_accel_mps2(("camera", "quadcopter")) == 2.5

    quadcopter = CATALOG.payload("quadcopter")
    assert quadcopter.name == "Small Quadcopter"
    assert "horizontal_control" in quadcopter.capabilities
    assert "camera_stabilization" in quadcopter.capabilities

    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("camera", "quadcopter"),
        launch_site_id="field",
        fill_mode=FillMode.NORMAL,
    )
    original = request.to_simulation_state()
    original.wind_enabled = True
    configured = configured_simulation_state(request, original)

    assert original.wind_enabled is True
    assert configured.wind_enabled is False


def test_aerostat_catalog_registration_is_idempotent():
    register_aerostat_catalog_extensions()
    register_aerostat_catalog_extensions()
