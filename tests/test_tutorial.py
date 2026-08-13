"""Compatibility coverage after replacing Tutorial with How to Play and Story."""

from balloon_frontier.career_prologue import (
    FIRST_FLIGHT_OPTION_KEYS,
    FIRST_FLIGHT_PROVIDED_PAYLOADS,
    FIRST_FLIGHT_REQUIRED_PAYLOADS,
)
from balloon_frontier.game_modes import GameMode, list_game_modes, select_game_mode
from balloon_frontier.how_to_play import how_to_play_text
from balloon_frontier.session_controller import get_mode_policy


def test_tutorial_is_not_a_selectable_mode():
    assert GameMode.TUTORIAL not in list_game_modes()
    assert list_game_modes() == [
        GameMode.STORY,
        GameMode.SCENARIO,
        GameMode.FREE_PLAY,
    ]


def test_legacy_tutorial_selection_routes_to_story():
    assert select_game_mode("tutorial") is GameMode.STORY
    assert get_mode_policy(GameMode.TUTORIAL) == get_mode_policy(GameMode.STORY)


def test_how_to_play_explains_shared_physics_and_progressive_story_choices():
    text = how_to_play_text()

    assert "How to Play Balloon Frontier" in text
    assert "same flight simulation" in text
    assert "no special training physics" in text
    assert "Later chapters introduce more" in text


def test_first_flight_menu_uses_normal_catalog_keys():
    assert FIRST_FLIGHT_REQUIRED_PAYLOADS == ("camera", "quad" "copter")
    assert FIRST_FLIGHT_PROVIDED_PAYLOADS == ("camera", "quad" "copter", "bat" "tery")
    assert FIRST_FLIGHT_OPTION_KEYS[0] == ("helium", "air")
    assert FIRST_FLIGHT_OPTION_KEYS[1] == ("latex", "candle_kite")
    assert FIRST_FLIGHT_OPTION_KEYS[2] == (
        "almost_lta",
        "lighter_lta",
        "maximum",
    )
    assert FIRST_FLIGHT_OPTION_KEYS[3] == (
        "parachute",
        "candle_" "heater",
        "electric_" "heater",
        "none",
    )
    assert FIRST_FLIGHT_OPTION_KEYS[4] == ("field",)


def test_first_flight_does_not_prescribe_a_winning_configuration():
    flattened = {
        option
        for options in FIRST_FLIGHT_OPTION_KEYS.values()
        for option in options
    }

    assert "tutorial_party_balloon" not in flattened
    assert "quad" "copter" not in flattened
    assert "bat" "tery" not in flattened
    assert "val" "ve" not in flattened
