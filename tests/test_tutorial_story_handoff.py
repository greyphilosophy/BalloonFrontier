import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from balloon_frontier.discord_ui import game_menu, modals
from balloon_frontier.game_modes import GameMode
from balloon_frontier.progression import PlayerRegistry, PlayerState


class _Interaction:
    def __init__(self, user_id="player"):
        self.user = SimpleNamespace(id=user_id)
        self.message = object()
        self.response = SimpleNamespace(edit_message=AsyncMock())
        self.edit_original_response = AsyncMock()


class _Parent:
    def __init__(self, *, mode=GameMode.TUTORIAL):
        self._game_entry_context = {
            "service": object(),
            "mode": mode,
            "player_id": "player",
            "channel_kind": "dm",
            "on_finished": None,
        }


def test_completed_tutorial_adds_continue_to_story_view(monkeypatch):
    player = PlayerState("player")
    player.missions_completed.append("first_flight")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )
    monkeypatch.setattr(modals.launch_handler, "run_launch", AsyncMock())

    interaction = _Interaction()
    button = modals._LaunchButton(_Parent(), service=object())
    asyncio.run(button.callback(interaction))

    modals.launch_handler.run_launch.assert_awaited_once()
    interaction.edit_original_response.assert_awaited_once()
    view = interaction.edit_original_response.await_args.kwargs["view"]
    assert isinstance(view, game_menu.ContinueToStoryView)
    assert view.player_id == "player"
    assert view.channel_kind == "dm"
    assert view.children[0].label == "Continue to Story Mode"


def test_failed_tutorial_does_not_offer_story_handoff(monkeypatch):
    player = PlayerState("player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )
    monkeypatch.setattr(modals.launch_handler, "run_launch", AsyncMock())

    interaction = _Interaction()
    button = modals._LaunchButton(_Parent(), service=object())
    asyncio.run(button.callback(interaction))

    interaction.edit_original_response.assert_not_awaited()


def test_non_tutorial_launch_never_adds_handoff(monkeypatch):
    player = PlayerState("player")
    player.missions_completed.append("first_flight")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )
    monkeypatch.setattr(modals.launch_handler, "run_launch", AsyncMock())

    interaction = _Interaction()
    button = modals._LaunchButton(_Parent(mode=GameMode.STORY), service=object())
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


def test_completed_players_see_replay_and_continue_labels(monkeypatch):
    player = PlayerState("player")
    player.missions_completed.append("first_flight")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )

    view = game_menu.GameModeView(
        player_id="player",
        channel_kind="dm",
        service=object(),
    )
    labels = {item.mode: item.label for item in view.children}

    assert labels[GameMode.TUTORIAL] == "Replay Tutorial"
    assert labels[GameMode.STORY] == "Continue Story"


def test_handoff_restricts_buttons_to_the_original_player():
    view = game_menu.ContinueToStoryView(
        player_id="player",
        channel_kind="dm",
        service=object(),
    )

    assert asyncio.run(view.interaction_check(_Interaction("player")))
    assert not asyncio.run(view.interaction_check(_Interaction("other")))
