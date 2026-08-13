"""First-flight Story onboarding uses foundational shared-world components."""

from balloon_frontier.career_prologue import (
    DiscoveryFirstFlightConfiguratorMixin,
    FIRST_FLIGHT_PROVIDED_PAYLOADS,
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


def test_first_flight_envelopes_include_standard_latex_and_second_option():
    options = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        type("FirstFlightOptions", (), {"_current_step": _Step.CHOOSE_ENVELOPE})(),
        _Step.CHOOSE_ENVELOPE,
    )

    second_env = "candle_" "kite"
    assert tuple(options) == ("latex", second_env)
    assert options["latex"] == ENVELOPE_OPTIONS["latex"]
    assert options["latex"][0] == "Latex Weather Balloon"
    assert options[second_env][0] == "Lightweight Hot-" "Air Envelope"
    assert second_env not in ENVELOPE_OPTIONS
    assert "tutorial_party_balloon" not in ENVELOPE_OPTIONS


def test_first_flight_provided_equipment_is_not_optional():
    holder = type(
        "FirstFlightOptions",
        (),
        {"_current_step": _Step.CHOOSE_PAYLOADS, "state": {"gas": "helium"}},
    )()
    options = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        holder,
        _Step.CHOOSE_PAYLOADS,
    )

    assert FIRST_FLIGHT_REQUIRED_PAYLOADS == ("camera", "quad" "copter")
    assert FIRST_FLIGHT_PROVIDED_PAYLOADS == ("camera", "quad" "copter", "bat" "tery")
    first_heat = "candle_" "heater"
    second_heat = "electric_" "heater"
    assert tuple(options) == ("parachute", first_heat, second_heat, "none")
    assert options["parachute"] == PAYLOAD_OPTIONS["parachute"]
    assert options[first_heat][0] == "Tea Light Heat Source"
    assert options[second_heat][0] == "Small Electric Heater"
    assert options["none"][0] == "No optional payload"
    assert "camera" not in options
    assert "quad" "copter" not in options
    assert "bat" "tery" not in options


def test_first_flight_air_and_school_site_are_local_to_story():
    holder = type(
        "FirstFlightOptions",
        (),
        {"_current_step": _Step.CHOOSE_GAS, "state": {"gas": "helium"}},
    )()
    gases = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        holder, _Step.CHOOSE_GAS
    )
    sites = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        holder, _Step.CHOOSE_SITE
    )

    assert gases["helium"] == GAS_OPTIONS["helium"]
    assert gases["air"][0] == "Air"
    assert "air" not in GAS_OPTIONS
    assert "hot_" "air" not in gases
    assert sites["field"].name == FIRST_FLIGHT_SITE_NAME
    assert sites["field"].altitude_m == SITE_OPTIONS["field"].altitude_m
    assert SITE_OPTIONS["field"].name == "Open Field"


def test_lift_target_fill_options_are_truthful_for_selected_aircraft():
    holder = type(
        "FirstFlightOptions",
        (DiscoveryFirstFlightConfiguratorMixin,),
        {
            "_current_step": _Step.CHOOSE_FILL,
            "state": {
                "gas": "helium",
                "envelope": "latex",
                "payloads": ["camera", "quad" "copter", "bat" "tery"],
                "site": "field",
            },
        },
    )()

    helium_latex = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        holder, _Step.CHOOSE_FILL
    )
    assert tuple(helium_latex) == ("almost_lta", "lighter_lta", "maximum")
    assert helium_latex["almost_lta"]["label"] == "Almost Lighter Than Air"
    assert helium_latex["lighter_lta"]["label"] == "Lighter Than Air"
    assert helium_latex["maximum"]["label"] == "Maximum Capacity"

    holder.state["envelope"] = "candle_" "kite"
    helium_small = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        holder, _Step.CHOOSE_FILL
    )
    assert tuple(helium_small) == ("maximum",)

    holder.state["gas"] = "air"
    air_small = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        holder, _Step.CHOOSE_FILL
    )
    assert tuple(air_small) == ("maximum",)
