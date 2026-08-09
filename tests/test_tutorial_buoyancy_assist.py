"""First-flight Story onboarding must use ordinary catalog equipment."""

from balloon_frontier.career_prologue import DiscoveryFirstFlightConfiguratorMixin
from balloon_frontier.discord_ui.configurator import (
    ENVELOPE_OPTIONS,
    GAS_OPTIONS,
    PAYLOAD_OPTIONS,
    SITE_OPTIONS,
    _Step,
)


def test_first_flight_envelope_is_the_standard_latex_weather_balloon():
    options = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        type("FirstFlightOptions", (), {"_current_step": _Step.CHOOSE_ENVELOPE})(),
        _Step.CHOOSE_ENVELOPE,
    )

    assert tuple(options) == ("latex",)
    assert options["latex"] is ENVELOPE_OPTIONS["latex"]
    assert options["latex"][0] == "Latex Weather Balloon"
    assert "tutorial_party_balloon" not in ENVELOPE_OPTIONS


def test_first_flight_uses_standard_camera_payload_not_special_quadcopter():
    options = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        type("FirstFlightOptions", (), {"_current_step": _Step.CHOOSE_PAYLOADS})(),
        _Step.CHOOSE_PAYLOADS,
    )

    assert tuple(options) == ("camera", "parachute", "none")
    assert options["camera"] is PAYLOAD_OPTIONS["camera"]
    assert "quadcopter" not in options


def test_first_flight_gases_and_site_are_normal_configurator_entries():
    holder = type("FirstFlightOptions", (), {"_current_step": _Step.CHOOSE_GAS})()
    gases = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        holder, _Step.CHOOSE_GAS
    )
    sites = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        holder, _Step.CHOOSE_SITE
    )

    assert gases["helium"] is GAS_OPTIONS["helium"]
    assert gases["hot_air"] is GAS_OPTIONS["hot_air"]
    assert sites["field"] is SITE_OPTIONS["field"]
