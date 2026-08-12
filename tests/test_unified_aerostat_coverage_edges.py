"""Coverage edges for the unified aerostat functional core."""

from balloon_frontier.aerostat import (
    fill_mass_for_configuration,
    register_aerostat_catalog_extensions,
)
from balloon_frontier.catalog import FillMode


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


def test_aerostat_catalog_registration_is_idempotent():
    register_aerostat_catalog_extensions()
    register_aerostat_catalog_extensions()
