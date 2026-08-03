"""Regression tests for the tutorial's buoyancy-assist aircraft."""

from balloon_frontier.catalog import CATALOG
from balloon_frontier.discord_ui.configurator import ENVELOPE_OPTIONS, PAYLOAD_OPTIONS
from balloon_frontier.tutorial import TutorialConfiguratorMixin
from balloon_frontier.tutorial_catalog import (
    QUADCOPTER,
    SCIENTIFIC_FILM_BALLOON_NAME,
    TUTORIAL_ASSIST_ENVELOPE,
    TUTORIAL_ENVELOPE_ID,
    ensure_discord_tutorial_options,
)


def test_tutorial_party_balloon_is_realistic_and_does_not_replace_scientific_film_balloon():
    ensure_discord_tutorial_options()

    tutorial_envelope = CATALOG.envelope(TUTORIAL_ENVELOPE_ID)
    shared_mylar = CATALOG.envelope("mylar")
    tutorial_options = TutorialConfiguratorMixin._tutorial_envelope_options()

    assert TUTORIAL_ENVELOPE_ID == "tutorial_party_balloon"
    assert tutorial_envelope is TUTORIAL_ASSIST_ENVELOPE
    assert tutorial_envelope.name == "Foil Party Balloon"
    assert tutorial_envelope.max_volume_m3 == 0.30
    assert tutorial_options["mylar"][0] == "Foil Party Balloon"
    assert tutorial_options["mylar"][1] == 0.30
    assert ENVELOPE_OPTIONS[TUTORIAL_ENVELOPE_ID][0] == "Foil Party Balloon"
    assert ENVELOPE_OPTIONS[TUTORIAL_ENVELOPE_ID][1] == 0.30

    approximate_gross_lift_kg = tutorial_envelope.max_volume_m3 * 1.05
    assert 0.25 <= approximate_gross_lift_kg <= 0.35

    assert shared_mylar is not tutorial_envelope
    assert shared_mylar.name == SCIENTIFIC_FILM_BALLOON_NAME
    assert shared_mylar.max_volume_m3 == 200.0
    assert ENVELOPE_OPTIONS["mylar"][0] == SCIENTIFIC_FILM_BALLOON_NAME
    assert ENVELOPE_OPTIONS["mylar"][1] == 200.0


def test_tutorial_quadcopter_is_the_powered_camera_aircraft():
    ensure_discord_tutorial_options()

    payload = CATALOG.payload("quadcopter")
    assert payload is QUADCOPTER
    assert payload.mass_kg == 0.25
    assert payload.has_valve is False
    assert "powered_flight" in payload.capabilities
    assert "radio_control" in payload.capabilities
    assert "camera" in payload.capabilities
    assert PAYLOAD_OPTIONS["quadcopter"][3] is False

    valve = CATALOG.payload("valve")
    assert valve.name == "Pressure Valve"
    assert valve.mass_kg == 0.3
    assert valve.cost == 250
    assert valve.has_valve is True
