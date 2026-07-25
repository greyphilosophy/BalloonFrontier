import pytest

from balloon_frontier.game_session import (
    GameMode,
    GameSession,
    list_game_modes,
    select_game_mode,
    DEFAULT_SIM_TIME_S,
    MISSION_SIM_TIME_S,
)
from balloon_frontier.launch_result import LaunchRequest, FillMode


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


def test_tutorial_disables_missions():
    req = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=(),
        launch_site_id="field",
        fill_mode=FillMode.NORMAL,
    )
    session = GameSession(player_id="p1", mode=GameMode.TUTORIAL)
    assignment = session.plan_mission_assignment(req)
    assert assignment.mission_ids == ()
    assert session.simulation_duration_s() == DEFAULT_SIM_TIME_S


def test_story_assigns_deterministic_missions_with_no_payloads():
    req = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=(),
        launch_site_id="field",
        fill_mode=FillMode.NORMAL,
    )
    session = GameSession(player_id="p1", mode=GameMode.STORY)

    a1 = session.plan_mission_assignment(req)
    a2 = session.plan_mission_assignment(req)

    assert a1.seed == a2.seed
    assert a1.mission_ids == a2.mission_ids

    # With empty payload selection, missions with required_payloads = []
    # should still be eligible.
    assert len(a1.mission_ids) >= 1


def test_mode_simulation_duration():
    assert GameMode.TUTORIAL.simulation_duration_s == DEFAULT_SIM_TIME_S
    assert GameMode.FREE_PLAY.simulation_duration_s == DEFAULT_SIM_TIME_S
    assert GameMode.STORY.simulation_duration_s == MISSION_SIM_TIME_S
    assert GameMode.SCENARIO.simulation_duration_s == MISSION_SIM_TIME_S
