import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from balloon_frontier.discord_ui import game_menu, modals
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import MissionResult
from balloon_frontier.story import EDGE_OF_SPACE_MISSION_ID, FIRST_FLIGHT_MISSION_ID


class _Interaction:
    def __init__(self, user_id="player"):
        self.user = SimpleNamespace(id=user_id)
        self.message = object()
        self.response = SimpleNamespace(edit_message=AsyncMock())
        self.edit_original_response = AsyncMock()


class _Parent:
    def __init__(self, *, mission_id=FIRST_FLIGHT_MISSION_ID):
        self._game_entry_context = {
            "service": object(),
            "mode": GameMode.STORY,
            "first_flight": mission_id == FIRST_FLIGHT_MISSION_ID,
            "story_mission_id": mission_id,
            "player_id": "player",
            "channel_kind": "dm",
            "on_finished": None,
        }


def _outcome(*, mission_id=FIRST_FLIGHT_MISSION_ID, completed: bool):
    return SimpleNamespace(
        mission_results=(
            MissionResult(
                mission_id=mission_id,
                completed=completed,
                reward=500 if completed else 0,
                explanation="mission result",
            ),
        )
    )


def test_completed_first_flight_fallback_adds_continue_story_view(monkeypatch):
    monkeypatch.setattr(
        modals.launch_handler,
        "run_launch",
        AsyncMock(return_value=_outcome(completed=True)),
    )

    interaction = _Interaction()
    button = modals._LaunchButton(_Parent(), service=object())
    asyncio.run(button.callback(interaction))

    interaction.edit_original_response.assert_awaited_once()
    view = interaction.edit_original_response.await_args.kwargs["view"]
    assert isinstance(view, game_menu.ContinueToStoryView)
    assert view.player_id == "player"
    assert view.channel_kind == "dm"
    assert view.children[0].label == "Continue Story"


def test_failed_first_flight_offers_mission_select_retry(monkeypatch):
    monkeypatch.setattr(
        modals.launch_handler,
        "run_launch",
        AsyncMock(return_value=_outcome(completed=False)),
    )

    interaction = _Interaction()
    button = modals._LaunchButton(_Parent(), service=object())
    asyncio.run(button.callback(interaction))

    interaction.edit_original_response.assert_awaited_once()
    view = interaction.edit_original_response.await_args.kwargs["view"]
    assert isinstance(view, game_menu.ContinueToStoryView)
    assert view.children[0].label == "Mission Select"


def test_ordinary_story_launch_returns_to_mission_select(monkeypatch):
    monkeypatch.setattr(
        modals.launch_handler,
        "run_launch",
        AsyncMock(
            return_value=_outcome(
                mission_id=EDGE_OF_SPACE_MISSION_ID,
                completed=True,
            )
        ),
    )

    interaction = _Interaction()
    button = modals._LaunchButton(
        _Parent(mission_id=EDGE_OF_SPACE_MISSION_ID),
        service=object(),
    )
    asyncio.run(button.callback(interaction))

    interaction.edit_original_response.assert_awaited_once()
    view = interaction.edit_original_response.await_args.kwargs["view"]
    assert isinstance(view, game_menu.ContinueToStoryView)
    assert view.children[0].label == "Mission Select"


def test_continue_button_opens_story_mission_select(monkeypatch):
    opened = AsyncMock()
    monkeypatch.setattr(game_menu, "show_story_mission_select", opened)
    view = game_menu.ContinueToStoryView(
        player_id="player",
        channel_kind="dm",
        service="root-service",
    )
    interaction = _Interaction()

    asyncio.run(view.children[0].callback(interaction))

    opened.assert_awaited_once_with(
        interaction,
        player_id="player",
        channel_kind="dm",
        service="root-service",
        on_finished=None,
        on_view_changed=None,
    )


def test_main_menu_has_how_to_play_and_no_tutorial_mode():
    view = game_menu.GameModeView(
        player_id="player",
        channel_kind="dm",
        service=object(),
    )
    mode_labels = {
        item.mode: item.label for item in view.children if hasattr(item, "mode")
    }

    assert GameMode.TUTORIAL not in mode_labels
    assert mode_labels[GameMode.STORY] == "Story"
    assert any(item.label == "How to Play" for item in view.children)


def test_configurator_restricts_every_step_to_the_original_player():
    configurator = game_menu._configurator_for_mode(
        service=object(),
        mode=GameMode.FREE_PLAY,
        player_id="player",
        channel_kind="dm",
        on_finished=None,
    )

    assert asyncio.run(configurator.interaction_check(_Interaction("player")))
    assert not asyncio.run(configurator.interaction_check(_Interaction("other")))


def test_handoff_restricts_buttons_to_the_original_player():
    view = game_menu.ContinueToStoryView(
        player_id="player",
        channel_kind="dm",
        service=object(),
    )

    assert asyncio.run(view.interaction_check(_Interaction("player")))
    assert not asyncio.run(view.interaction_check(_Interaction("other")))
