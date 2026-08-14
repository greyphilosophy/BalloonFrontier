"""Acceptance tests for Story mission selection, replay, and back navigation."""

import asyncio
from types import SimpleNamespace

import pytest

from balloon_frontier.discord_ui import game_menu
from balloon_frontier.discord_ui.configurator import _Step
from balloon_frontier.game_modes import GameMode
from balloon_frontier.progression import PlayerRegistry, PlayerState
from balloon_frontier.session_controller import assign_missions_for_mode
from balloon_frontier.story import (
    ATMOSPHERIC_RIVER_MISSION_ID,
    EDGE_OF_SPACE_MISSION_ID,
    FIRST_FLIGHT_MISSION_ID,
)
from balloon_frontier.story_mission_select import story_mission_choices


class FakeResponse:
    def __init__(self):
        self.edited = None

    async def edit_message(self, *, content, view):
        self.edited = (content, view)


class FakeInteraction:
    def __init__(self, user_id="player"):
        self.user = SimpleNamespace(id=user_id)
        self.message = object()
        self.response = FakeResponse()


def _player(monkeypatch, completed=()):
    player = PlayerState("player")
    player.missions_completed.extend(completed)
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )
    return player


def test_fresh_player_sees_only_first_flight_as_next(monkeypatch):
    _player(monkeypatch)

    choices = story_mission_choices("player")

    assert [choice.chapter.mission_id for choice in choices] == [FIRST_FLIGHT_MISSION_ID]
    assert [choice.completed for choice in choices] == [False]
    assert [choice.is_next for choice in choices] == [True]


def test_completed_missions_are_replayable_and_only_next_incomplete_is_visible(monkeypatch):
    _player(monkeypatch, completed=(FIRST_FLIGHT_MISSION_ID,))

    choices = story_mission_choices("player")

    assert [choice.chapter.mission_id for choice in choices] == [
        FIRST_FLIGHT_MISSION_ID,
        EDGE_OF_SPACE_MISSION_ID,
    ]
    assert [choice.completed for choice in choices] == [True, False]
    assert [choice.is_next for choice in choices] == [False, True]
    assert ATMOSPHERIC_RIVER_MISSION_ID not in {
        choice.chapter.mission_id for choice in choices
    }


def test_all_completed_story_missions_remain_available_for_replay(monkeypatch):
    _player(
        monkeypatch,
        completed=(
            FIRST_FLIGHT_MISSION_ID,
            EDGE_OF_SPACE_MISSION_ID,
            ATMOSPHERIC_RIVER_MISSION_ID,
        ),
    )

    choices = story_mission_choices("player")

    assert [choice.chapter.mission_id for choice in choices] == [
        FIRST_FLIGHT_MISSION_ID,
        EDGE_OF_SPACE_MISSION_ID,
        ATMOSPHERIC_RIVER_MISSION_ID,
    ]
    assert all(choice.completed for choice in choices)
    assert not any(choice.is_next for choice in choices)


def test_story_mode_opens_mission_select_instead_of_configuration(monkeypatch):
    _player(monkeypatch)
    interaction = FakeInteraction()
    modes = game_menu.GameModeView(
        player_id="player",
        channel_kind="dm",
        service=object(),
    )

    asyncio.run(modes.select_mode(interaction, GameMode.STORY))

    content, view = interaction.response.edited
    assert isinstance(view, game_menu.StoryMissionSelectView)
    assert "Story Missions" in content
    assert [item.mission_id for item in view.children if hasattr(item, "mission_id")] == [
        FIRST_FLIGHT_MISSION_ID
    ]


def test_mission_select_marks_completed_as_replay_and_next_as_next(monkeypatch):
    _player(monkeypatch, completed=(FIRST_FLIGHT_MISSION_ID,))

    view = game_menu.StoryMissionSelectView(
        player_id="player",
        channel_kind="dm",
        service=object(),
    )
    labels = {
        item.mission_id: item.label
        for item in view.children
        if hasattr(item, "mission_id")
    }

    assert "Replay" in labels[FIRST_FLIGHT_MISSION_ID]
    assert "Next" in labels[EDGE_OF_SPACE_MISSION_ID]
    assert ATMOSPHERIC_RIVER_MISSION_ID not in labels


def test_replaying_first_flight_uses_first_flight_menu_and_briefing_after_completion(monkeypatch):
    _player(monkeypatch, completed=(FIRST_FLIGHT_MISSION_ID, EDGE_OF_SPACE_MISSION_ID))

    configurator = game_menu._configurator_for_mode(
        service=object(),
        mode=GameMode.STORY,
        player_id="player",
        channel_kind="dm",
        on_finished=None,
        story_mission_id=FIRST_FLIGHT_MISSION_ID,
    )

    assert configurator._game_entry_context["story_mission_id"] == FIRST_FLIGHT_MISSION_ID
    assert configurator._game_entry_context["first_flight"] is True
    assert configurator._service.service.story_mission_id == FIRST_FLIGHT_MISSION_ID
    content = configurator._step_content()
    assert "Your First Flight" in content
    assert "Summer Project: Edge of Space" not in content
    assert "Atmospheric River" not in content


def test_replaying_completed_edge_of_space_shows_edge_of_space_briefing(monkeypatch):
    _player(monkeypatch, completed=(FIRST_FLIGHT_MISSION_ID, EDGE_OF_SPACE_MISSION_ID))

    configurator = game_menu._configurator_for_mode(
        service=object(),
        mode=GameMode.STORY,
        player_id="player",
        channel_kind="dm",
        on_finished=None,
        story_mission_id=EDGE_OF_SPACE_MISSION_ID,
    )

    content = configurator._step_content()
    assert "Summer Project: Edge of Space" in content
    assert "Atmospheric River" not in content


def test_selected_story_mission_overrides_progression_default(monkeypatch):
    _player(monkeypatch, completed=(FIRST_FLIGHT_MISSION_ID,))
    configuration = {
        "gas": "helium",
        "envelope": "latex",
        "payloads": ("camera",),
        "site": "field",
        "fill_mode": "auto",
    }

    missions = assign_missions_for_mode(
        GameMode.STORY,
        configuration,
        player_id="player",
        context={"story_mission_id": FIRST_FLIGHT_MISSION_ID},
    )

    assert missions == (FIRST_FLIGHT_MISSION_ID,)


def test_locked_future_story_mission_cannot_be_selected(monkeypatch):
    _player(monkeypatch)
    configuration = {
        "gas": "helium",
        "envelope": "latex",
        "payloads": ("camera",),
        "site": "field",
        "fill_mode": "auto",
    }

    with pytest.raises(ValueError, match="not unlocked"):
        assign_missions_for_mode(
            GameMode.STORY,
            configuration,
            player_id="player",
            context={"story_mission_id": EDGE_OF_SPACE_MISSION_ID},
        )


def test_back_from_first_configuration_step_returns_to_mission_select(monkeypatch):
    _player(monkeypatch)
    configurator = game_menu._configurator_for_mode(
        service=object(),
        mode=GameMode.STORY,
        player_id="player",
        channel_kind="dm",
        on_finished=None,
        story_mission_id=FIRST_FLIGHT_MISSION_ID,
    )
    interaction = FakeInteraction()

    asyncio.run(configurator._on_back(interaction))

    content, view = interaction.response.edited
    assert isinstance(view, game_menu.StoryMissionSelectView)
    assert "Story Missions" in content


def test_back_from_later_configuration_step_stays_in_configuration(monkeypatch):
    _player(monkeypatch)
    configurator = game_menu._configurator_for_mode(
        service=object(),
        mode=GameMode.STORY,
        player_id="player",
        channel_kind="dm",
        on_finished=None,
        story_mission_id=FIRST_FLIGHT_MISSION_ID,
    )
    configurator._current_step = _Step.CHOOSE_FILL
    configurator.build_buttons()
    interaction = FakeInteraction()

    asyncio.run(configurator._on_back(interaction))

    assert configurator._current_step == _Step.CHOOSE_SITE
    assert interaction.response.edited[1] is configurator


def test_back_from_first_free_play_step_returns_to_modes():
    configurator = game_menu._configurator_for_mode(
        service=object(),
        mode=GameMode.FREE_PLAY,
        player_id="player",
        channel_kind="dm",
        on_finished=None,
    )
    interaction = FakeInteraction()

    asyncio.run(configurator._on_back(interaction))

    content, view = interaction.response.edited
    assert isinstance(view, game_menu.GameModeView)
    assert "Balloon Frontier" in content


def test_mission_select_back_returns_to_modes(monkeypatch):
    _player(monkeypatch)
    view = game_menu.StoryMissionSelectView(
        player_id="player",
        channel_kind="dm",
        service=object(),
    )
    interaction = FakeInteraction()
    back = next(item for item in view.children if item.label == "Back to Modes")

    asyncio.run(back.callback(interaction))

    content, destination = interaction.response.edited
    assert isinstance(destination, game_menu.GameModeView)
    assert "Balloon Frontier" in content


def test_continue_story_opens_mission_select(monkeypatch):
    _player(monkeypatch, completed=(FIRST_FLIGHT_MISSION_ID,))
    view = game_menu.ContinueToStoryView(
        player_id="player",
        channel_kind="dm",
        service=object(),
    )
    interaction = FakeInteraction()

    asyncio.run(view.children[0].callback(interaction))

    content, destination = interaction.response.edited
    assert isinstance(destination, game_menu.StoryMissionSelectView)
    assert "Story Missions" in content
