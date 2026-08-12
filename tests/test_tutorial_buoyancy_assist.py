"""First-flight Story onboarding uses foundational shared-world components."""

from balloon_frontier.career_prologue import DiscoveryFirstFlightConfiguratorMixin
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
    assert options["latex"] is ENVELOPE_OPTIONS["latex"]
    assert options["latex"][0] == "Latex Weather Balloon"
    assert options["candle_kite"] is ENVELOPE_OPTIONS["candle_kite"]
    assert options["candle_kite"][0] == "Lightweight Hot-Air Envelope"
    assert "tutorial_party_balloon" not in ENVELOPE_OPTIONS


def test_first_flight_payloads_include_heat_sources_without_special_quadcopter():
    options = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        type("FirstFlightOptions", (), {"_current_step": _Step.CHOOSE_PAYLOADS})(),
        _Step.CHOOSE_PAYLOADS,
    )

    assert tuple(options) == (
        "camera",
        "parachute",
        "candle_heater",
        "electric_heater",
        "none",
    )
    assert options["camera"] is PAYLOAD_OPTIONS["camera"]
    assert options["candle_heater"] is PAYLOAD_OPTIONS["candle_heater"]
    assert options["electric_heater"] is PAYLOAD_OPTIONS["electric_heater"]
    assert "quadcopter" not in options
    assert "valve" not in options


def test_first_flight_air_and_site_are_normal_configurator_entries():
    holder = type("FirstFlightOptions", (), {"_current_step": _Step.CHOOSE_GAS})()
    gases = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        holder, _Step.CHOOSE_GAS
    )
    sites = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        holder, _Step.CHOOSE_SITE
    )

    assert gases["helium"] is GAS_OPTIONS["helium"]
    assert gases["air"] is GAS_OPTIONS["air"]
    assert "hot_air" not in gases
    assert sites["field"] is SITE_OPTIONS["field"]
