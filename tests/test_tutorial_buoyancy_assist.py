"""First-flight Story onboarding uses truthful shared-world balloon physics."""

import pytest

from balloon_frontier.catalog import CATALOG
from balloon_frontier.career_prologue import (
    DiscoveryFirstFlightConfiguratorMixin,
    FIRST_FLIGHT_PROVIDED_PAYLOADS,
    FIRST_FLIGHT_REQUIRED_PAYLOADS,
    FIRST_FLIGHT_SITE_NAME,
)
from balloon_frontier.discord_ui.configurator import (
    GAS_OPTIONS,
    PAYLOAD_OPTIONS,
    SITE_OPTIONS,
    _Step,
)


def test_first_flight_helium_balloon_choices_are_small_to_large():
    holder = type(
        "FirstFlightOptions",
        (),
        {"_current_step": _Step.CHOOSE_ENVELOPE, "state": {"gas": "helium"}},
    )()
    options = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        holder,
        _Step.CHOOSE_ENVELOPE,
    )

    assert tuple(options) == ("s45", "s55", "s70")
    assert options["s45"][0] == '45" Latex Weather Balloon'
    assert options["s55"][0] == '55" Latex Weather Balloon'
    assert options["s70"][0] == '70" Latex Weather Balloon'
    assert [options[key][2] for key in options] == [
        CATALOG.balloon("s45").mass_kg,
        CATALOG.balloon("s55").mass_kg,
        CATALOG.balloon("s70").mass_kg,
    ]
    assert [options[key][5] for key in options] == [15, 25, 45]


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
    assert tuple(options) == ("parachute", "none")
    assert options["parachute"] == PAYLOAD_OPTIONS["parachute"]
    assert options["none"][0] == "No optional payload"
    assert "camera" not in options
    assert "quad" "copter" not in options
    assert "bat" "tery" not in options
    assert "candle_" "heater" not in options
    assert "electric_" "heater" not in options


def test_first_flight_provides_helium_and_keeps_school_site_local_to_story():
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

    assert tuple(gases) == ("helium",)
    assert gases["helium"] == GAS_OPTIONS["helium"]
    assert "air" not in gases
    assert sites["field"].name == FIRST_FLIGHT_SITE_NAME
    assert sites["field"].altitude_m == SITE_OPTIONS["field"].altitude_m
    assert SITE_OPTIONS["field"].name == "Open Field"


def test_lift_target_fill_options_are_truthful_for_selected_balloon_size():
    holder = type(
        "FirstFlightOptions",
        (DiscoveryFirstFlightConfiguratorMixin,),
        {
            "_current_step": _Step.CHOOSE_FILL,
            "state": {
                "gas": "helium",
                "envelope": "latex",
                "balloon_size": "s45",
                "_first_flight_balloon_choice": "s45",
                "payloads": ["camera", "quad" "copter", "bat" "tery"],
                "site": "field",
            },
        },
    )()

    options = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        holder, _Step.CHOOSE_FILL
    )
    assert tuple(options) == ("almost_lta", "lighter_lta", "maximum")
    assert options["almost_lta"]["label"] == "Almost Lighter Than Air"
    assert options["lighter_lta"]["label"] == "Lighter Than Air"
    assert options["maximum"]["label"] == "Maximum Capacity"

    # Larger First Flight balloons preserve the same semantic fill choices while
    # changing the real envelope mass/volume/burst properties underneath them.
    holder.state["balloon_size"] = "s70"
    holder.state["_first_flight_balloon_choice"] = "s70"
    larger = DiscoveryFirstFlightConfiguratorMixin._first_flight_options(
        holder, _Step.CHOOSE_FILL
    )
    assert tuple(larger) == ("almost_lta", "lighter_lta", "maximum")


def test_semantic_fill_target_recalculates_when_payload_mass_changes():
    holder = type(
        "FirstFlightOptions",
        (DiscoveryFirstFlightConfiguratorMixin,),
        {
            "state": {
                "gas": "helium",
                "envelope": "latex",
                "balloon_size": "s55",
                "_first_flight_balloon_choice": "s55",
                "payloads": ["camera", "quad" "copter", "bat" "tery"],
                "site": "field",
                "fill_mode": "manual",
                "manual_gas_mass": None,
                "gas_mass": None,
                "_first_flight_fill_key": "almost_lta",
                "_first_flight_fill_label": "Almost Lighter Than Air",
            },
        },
    )()

    initial_mass = round(holder._first_flight_fill_mass("almost_lta"), 3)
    holder.state["manual_gas_mass"] = initial_mass
    holder.state["gas_mass"] = initial_mass
    holder.state["payloads"].append("parachute")

    assert holder._refresh_first_flight_fill_target() is True
    expected_mass = round(holder._first_flight_fill_mass("almost_lta"), 3)
    assert holder.state["gas_mass"] == pytest.approx(expected_mass)
    assert holder.state["manual_gas_mass"] == pytest.approx(expected_mass)
    assert holder.state["gas_mass"] > initial_mass
    assert holder.state["fill_mode"] == "manual"
    assert holder.state["_first_flight_fill_key"] == "almost_lta"
    assert holder.state["_first_flight_fill_label"] == "Almost Lighter Than Air"


def test_smallest_balloon_invalidates_semantic_target_after_heavy_optional_payload():
    holder = type(
        "FirstFlightOptions",
        (DiscoveryFirstFlightConfiguratorMixin,),
        {
            "state": {
                "gas": "helium",
                "envelope": "latex",
                "balloon_size": "s45",
                "_first_flight_balloon_choice": "s45",
                "payloads": [
                    "camera",
                    "quad" "copter",
                    "bat" "tery",
                    "parachute",
                ],
                "site": "field",
                "fill_mode": "manual",
                "manual_gas_mass": 0.5,
                "gas_mass": 0.5,
                "_first_flight_fill_key": "almost_lta",
                "_first_flight_fill_label": "Almost Lighter Than Air",
            },
        },
    )()

    assert holder._refresh_first_flight_fill_target() is False
    assert "_first_flight_fill_key" not in holder.state
    assert "_first_flight_fill_label" not in holder.state
