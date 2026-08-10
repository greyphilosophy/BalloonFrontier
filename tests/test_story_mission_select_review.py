"""Review regressions for Story mission completion and assignment safety."""

from types import SimpleNamespace

import pytest

from balloon_frontier import session_controller as controller
from balloon_frontier.discord_ui.game_menu import ContinueToStoryView
from balloon_frontier.game_modes import GameMode
from balloon_frontier.progression import PlayerRegistry, PlayerState
from balloon_frontier.story import EDGE_OF_SPACE_MISSION_ID, FIRST_FLIGHT_MISSION_ID
from balloon_frontier.tutorial_result_delivery import _build_next_action_view


def _player(monkeypatch, completed=()):
    player = PlayerState("player")
    player.missions_completed.extend(completed)
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )
    return player


def test_completed_later_story_mission_gets_mission_select_continuation(monkeypatch):
    _player(monkeypatch, completed=(FIRST_FLIGHT_MISSION_ID,))
    remembered = []
    configurator = SimpleNamespace(
        _game_entry_context={
            "mode": GameMode.STORY,
            "story_mission_id": EDGE_OF_SPACE_MISSION_ID,
            "first_flight": False,
            "player_id": "player",
            "channel_kind": "dm",
            "service": object(),
            "on_finished": None,
            "on_view_changed": remembered.append,
        }
    )
    interaction = SimpleNamespace(user=SimpleNamespace(id="player"))
    result = SimpleNamespace(
        mission_results=(
            SimpleNamespace(
                mission_id=EDGE_OF_SPACE_MISSION_ID,
                completed=True,
            ),
        )
    )

    view = _build_next_action_view(configurator, interaction, result)

    assert isinstance(view, ContinueToStoryView)
    assert "Edge of Space" in view._resume_content
    assert remembered == [view]


def test_incomplete_story_mission_does_not_get_completion_continuation(monkeypatch):
    _player(monkeypatch, completed=(FIRST_FLIGHT_MISSION_ID,))
    configurator = SimpleNamespace(
        _game_entry_context={
            "mode": GameMode.STORY,
            "story_mission_id": EDGE_OF_SPACE_MISSION_ID,
            "first_flight": False,
            "player_id": "player",
            "channel_kind": "dm",
            "service": object(),
            "on_finished": None,
        }
    )
    interaction = SimpleNamespace(user=SimpleNamespace(id="player"))
    result = SimpleNamespace(
        mission_results=(
            SimpleNamespace(
                mission_id=EDGE_OF_SPACE_MISSION_ID,
                completed=False,
            ),
        )
    )

    assert _build_next_action_view(configurator, interaction, result) is None


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
