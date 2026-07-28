"""Regression tests for the tutorial's buoyancy-assist aircraft."""

from balloon_frontier.catalog import CATALOG
from balloon_frontier.discord_ui.configurator import ENVELOPE_OPTIONS, PAYLOAD_OPTIONS
from balloon_frontier.tutorial_catalog import (
    QUADCOPTER,
    TUTORIAL_ASSIST_ENVELOPE,
    ensure_discord_tutorial_options,
)


def test_tutorial_balloon_is_small_buoyancy_assist_not_heavy_lift_envelope():
    ensure_discord_tutorial_options()

    envelope = CATALOG.envelope("mylar")
    assert envelope is TUTORIAL_ASSIST_ENVELOPE
    assert envelope.max_volume_m3 == 0.30
    assert ENVELOPE_OPTIONS["mylar"][1] == 0.30

    # Sea-level helium provides about 1.05 kg of gross lift per cubic metre.
    # A 0.30 m³ envelope therefore assists a 0.25 kg aircraft without turning
    # the quadcopter into a token motor beneath a heavy-lift balloon.
    approximate_gross_lift_kg = envelope.max_volume_m3 * 1.05
    assert 0.25 <= approximate_gross_lift_kg <= 0.35


def test_tutorial_quadcopter_has_integrated_pressure_relief():
    ensure_discord_tutorial_options()

    payload = CATALOG.payload("quadcopter")
    assert payload is QUADCOPTER
    assert payload.mass_kg == 0.25
    assert payload.has_valve
    assert "automatic_venting" in payload.capabilities
    assert PAYLOAD_OPTIONS["quadcopter"][3] is True
