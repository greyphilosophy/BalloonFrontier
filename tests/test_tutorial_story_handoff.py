import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from balloon_frontier.discord_ui import game_menu, modals
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import MissionResult


class _Interaction:
    def __init__(self, user_id="player"):
        self.user = SimpleNamespace(id=user_id)
        self.message = object()
        self.response = SimpleNamespace(edit_message=AsyncMock())
        self.edit_original_response = AsyncMock()


class _Parent:
    def __init__(self, *, first_flight=True):
        self._game_entry_context = {
            "service": object(),
            "mode": GameMode.STORY,
            "first_flight": first_flight,
            "player_id": "player",
            "channel_kind": "dm",
            "on_finished": None,
        }


def _outcome(*, completed: bool):
    return SimpleNamespace(
        mission_results=(
            MissionResult(
                mission_id="first_flight",
                completed=completed,
                reward=500 if completed else 0,
                explanation="first-flight result",
            ),
        )
    )


def test_completed_first_flight_adds_continue_story_view(monkeypatch):
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


def test_failed_first_flight_does_not_offer_handoff(monkeypatch):
    monkeypatch.setattr(
        modals.launch_handler,
        "run_launch",
        AsyncMock(return_value=_outcome(completed=False)),
    )

    interaction = _Interaction()
    button = modals._LaunchButton(_Parent(), service=object())
    asyncio.run(button.callback(interaction))

    interaction.edit_original_response.assert_not_awaited()


def test_ordinary_story_launch_does_not_use_first_flight_handoff(monkeypatch):
    monkeypatch.setattr(
        modals.launch_handler,
        "run_launch",
        AsyncMock(return_value=_outcome(completed=True)),
    )

    interaction = _Interaction()
    button = modals._LaunchButton(_Parent(first_flight=False), service=object())
    asyncio.run(button.callback(interaction))

    interaction.edit_original_response.assert_not_awaited()


def test_continue_button_opens_story_mode(monkeypatch):
    started = AsyncMock()
    monkeypatch.setattr(game_menu, "start_mode", started)
    view = game_menu.ContinueToStoryView(
        player_id="player",
        channel_kind="dm",
        service="root-service",
    )
    interaction = _Interaction()

    asyncio.run(view.children[0].callback(interaction))

    started.assert_awaited_once_with(
        interaction,
        service="root-service",
        mode=GameMode.STORY,
        player_id="player",
        channel_kind="dm",
        on_finished=None,
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
