"""First-flight Story onboarding uses foundational shared-world components."""

from balloon_frontier.career_prologue import (
    DiscoveryFirstFlightConfiguratorMixin,
    FIRST_FLIGHT_REQUIRED_PAYLOADS,
    FIRST_FLIGHT_SITE_NAME,
)
from balloon_frontier.discord_ui.configurator import (
    ENVELOPE_OPTIONS,
    GAS_OPTIONS,
    PAYLOAD_OPTIONS,
    SITE_OPTIONS,
    _Step,
)


def test_first_flight_envelopes_include_standard_latex_and_heated_air_option():
    options = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        type("FirstFlightOptions", (), {"_current_step": _Step.CHOOSE_ENVELOPE})(),
        _Step.CHOOSE_ENVELOPE,
    )

    assert tuple(options) == ("latex", "candle_kite")
    assert options["latex"] == ENVELOPE_OPTIONS["latex"]
    assert options["latex"][0] == "Latex Weather Balloon"
    assert options["candle_kite"][0] == "Lightweight Hot-Air Envelope"
    assert "candle_kite" not in ENVELOPE_OPTIONS
    assert "tutorial_party_balloon" not in ENVELOPE_OPTIONS


def test_first_flight_required_camera_and_quadcopter_are_not_optional_toggles():
    options = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        type("FirstFlightOptions", (), {"_current_step": _Step.CHOOSE_PAYLOADS})(),
        _Step.CHOOSE_PAYLOADS,
    )

    assert FIRST_FLIGHT_REQUIRED_PAYLOADS == ("camera", "quadcopter")
    assert tuple(options) == (
        "parachute",
        "candle_heater",
        "electric_heater",
        "none",
    )
    assert options["parachute"] == PAYLOAD_OPTIONS["parachute"]
    assert options["candle_heater"][0] == "Tea Light Heat Source"
    assert options["electric_heater"][0] == "Small Electric Heater"
    assert options["none"][0] == "No optional payload"
    assert "camera" not in options
    assert "quadcopter" not in options
    assert "valve" not in options


def test_first_flight_air_and_school_site_are_local_to_story():
    holder = type("FirstFlightOptions", (), {"_current_step": _Step.CHOOSE_GAS})()
    gases = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        holder, _Step.CHOOSE_GAS
    )
    sites = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        holder, _Step.CHOOSE_SITE
    )

    assert gases["helium"] == GAS_OPTIONS["helium"]
    assert gases["air"][0] == "Air"
    assert "air" not in GAS_OPTIONS
    assert "hot_air" not in gases
    assert sites["field"].name == FIRST_FLIGHT_SITE_NAME
    assert sites["field"].altitude_m == SITE_OPTIONS["field"].altitude_m
    assert SITE_OPTIONS["field"].name == "Open Field"
