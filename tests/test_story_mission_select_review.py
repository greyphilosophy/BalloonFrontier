"""Review regressions for Story mission completion and assignment safety."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from balloon_frontier import session_controller as controller
from balloon_frontier.discord_ui import launch_handler, modals
from balloon_frontier.discord_ui.game_menu import ContinueToStoryView
from balloon_frontier.game_modes import GameMode
from balloon_frontier.progression import PlayerRegistry, PlayerState
from balloon_frontier.story import EDGE_OF_SPACE_MISSION_ID, FIRST_FLIGHT_MISSION_ID


def _player(monkeypatch, completed=()):
    player = PlayerState("player")
    player.missions_completed.extend(completed)
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )
    return player


def _story_parent(*, mission_id=EDGE_OF_SPACE_MISSION_ID):
    return SimpleNamespace(
        _game_entry_context={
            "mode": GameMode.STORY,
            "story_mission_id": mission_id,
            "first_flight": mission_id == FIRST_FLIGHT_MISSION_ID,
            "player_id": "player",
            "channel_kind": "dm",
            "service": object(),
            "on_finished": None,
            "on_view_changed": None,
        }
    )


def _interaction():
    return SimpleNamespace(
        user=SimpleNamespace(id="player"),
        edit_original_response=AsyncMock(),
    )


def _outcome(mission_id, *, completed):
    return SimpleNamespace(
        mission_results=(
            SimpleNamespace(mission_id=mission_id, completed=completed),
        )
    )


def test_completed_later_story_mission_gets_mission_select_continuation(monkeypatch):
    _player(monkeypatch, completed=(FIRST_FLIGHT_MISSION_ID,))
    parent = _story_parent()
    interaction = _interaction()
    monkeypatch.setattr(
        launch_handler,
        "run_launch",
        AsyncMock(return_value=_outcome(EDGE_OF_SPACE_MISSION_ID, completed=True)),
    )

    button = modals._LaunchButton(parent, service=object())
    asyncio.run(button.callback(interaction))

    interaction.edit_original_response.assert_awaited_once()
    view = interaction.edit_original_response.await_args.kwargs["view"]
    assert isinstance(view, ContinueToStoryView)
    assert "Edge of Space" in view._resume_content
    assert "Complete" in view._resume_content
    assert view.children[0].label == "Mission Select"


def test_failed_later_story_mission_still_gets_retry_navigation(monkeypatch):
    _player(monkeypatch, completed=(FIRST_FLIGHT_MISSION_ID,))
    parent = _story_parent()
    interaction = _interaction()
    monkeypatch.setattr(
        launch_handler,
        "run_launch",
        AsyncMock(return_value=_outcome(EDGE_OF_SPACE_MISSION_ID, completed=False)),
    )

    button = modals._LaunchButton(parent, service=object())
    asyncio.run(button.callback(interaction))

    interaction.edit_original_response.assert_awaited_once()
    view = interaction.edit_original_response.await_args.kwargs["view"]
    assert isinstance(view, ContinueToStoryView)
    assert "Attempt Finished" in view._resume_content
    assert view.children[0].label == "Mission Select"


def test_failed_first_flight_still_gets_mission_select_retry(monkeypatch):
    _player(monkeypatch)
    parent = _story_parent(mission_id=FIRST_FLIGHT_MISSION_ID)
    interaction = _interaction()
    monkeypatch.setattr(
        launch_handler,
        "run_launch",
        AsyncMock(return_value=_outcome(FIRST_FLIGHT_MISSION_ID, completed=False)),
    )

    button = modals._LaunchButton(parent, service=object())
    asyncio.run(button.callback(interaction))

    interaction.edit_original_response.assert_awaited_once()
    view = interaction.edit_original_response.await_args.kwargs["view"]
    assert isinstance(view, ContinueToStoryView)
    assert "Attempt Finished" in view._resume_content
    assert view.children[0].label == "Mission Select"


def test_missing_selected_story_mission_definition_never_falls_back(monkeypatch):
    _player(monkeypatch, completed=(FIRST_FLIGHT_MISSION_ID,))
    monkeypatch.setattr(controller, "ensure_missions_loaded", lambda mission_dir=None: None)
    monkeypatch.delitem(controller.MISSIONS, EDGE_OF_SPACE_MISSION_ID, raising=False)
    selected = []
    monkeypatch.setattr(
        controller,
        "select_missions",
        lambda **kwargs: selected.append(kwargs) or ["unrelated"],
    )

    with pytest.raises(LookupError, match="Story mission definition"):
        controller.assign_missions_for_mode(
            GameMode.STORY,
            {
                "gas": "helium",
                "envelope": "latex",
                "payloads": ("camera",),
                "site": "field",
                "fill_mode": "auto",
            },
            player_id="player",
            context={"story_mission_id": EDGE_OF_SPACE_MISSION_ID},
        )

    assert selected == []
