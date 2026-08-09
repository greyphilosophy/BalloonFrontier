import pytest

from balloon_frontier.game_modes import GameMode, list_game_modes, select_game_mode


def test_list_game_modes_excludes_legacy_tutorial():
    assert list_game_modes() == [
        GameMode.STORY,
        GameMode.SCENARIO,
        GameMode.FREE_PLAY,
    ]


@pytest.mark.parametrize(
    "value,expected",
    [
        (1, GameMode.STORY),
        (2, GameMode.SCENARIO),
        (3, GameMode.FREE_PLAY),
        ("tutorial", GameMode.STORY),
        ("Story", GameMode.STORY),
        ("scenario", GameMode.SCENARIO),
        ("free play", GameMode.FREE_PLAY),
        ("free-play", GameMode.FREE_PLAY),
    ],
)
def test_select_game_mode(value, expected):
    assert select_game_mode(value) == expected


def test_select_game_mode_rejects_unknown():
    with pytest.raises(ValueError):
        select_game_mode("nope")


def test_visible_game_mode_labels_and_descriptions_are_defined():
    assert GameMode.STORY.label == "Story"
    assert GameMode.SCENARIO.label == "Scenario"
    assert GameMode.FREE_PLAY.label == "Free Play"
    for mode in list_game_modes():
        assert mode.description


def test_legacy_tutorial_enum_is_not_player_facing():
    assert GameMode.TUTORIAL not in list_game_modes()
    assert GameMode.TUTORIAL.description == "Legacy alias for Story onboarding."
