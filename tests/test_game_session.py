import pytest

from balloon_frontier.game_modes import GameMode, list_game_modes, select_game_mode


def test_list_game_modes_order():
    modes = list_game_modes()
    assert modes == [
        GameMode.TUTORIAL,
        GameMode.STORY,
        GameMode.SCENARIO,
        GameMode.FREE_PLAY,
    ]


@pytest.mark.parametrize(
    "value,expected",
    [
        (1, GameMode.TUTORIAL),
        (2, GameMode.STORY),
        (3, GameMode.SCENARIO),
        (4, GameMode.FREE_PLAY),
        ("tutorial", GameMode.TUTORIAL),
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


def test_game_mode_labels_and_descriptions_are_defined():
    assert GameMode.TUTORIAL.label == "Tutorial"
    assert GameMode.STORY.label == "Story"
    assert GameMode.SCENARIO.label == "Scenario"
    assert GameMode.FREE_PLAY.label == "Free Play"

    # Smoke-test that descriptions exist (non-empty) for UX.
    for mode in list_game_modes():
        assert mode.description
