import asyncio
from types import SimpleNamespace

from balloon_frontier.game_modes import GameMode, list_game_modes
from balloon_frontier.discord_ui import game_menu


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


class FakeConfigurator:
    def __init__(self, service):
        self.service = service
        self._msg = None

    def _step_content(self):
        return "configuration step"


class FakeDestination:
    def __init__(self):
        self.sent = []

    async def send(self, content, view=None):
        message = SimpleNamespace(content=content, view=view)
        self.sent.append(message)
        return message


def test_mode_menu_lists_playable_modes_plus_how_to_play_and_restricts_interactions():
    view = game_menu.GameModeView(
        player_id="player",
        channel_kind="dm",
        service=object(),
    )

    mode_children = [item for item in view.children if hasattr(item, "mode")]
    assert [item.mode for item in mode_children] == list_game_modes()
    assert GameMode.TUTORIAL not in [item.mode for item in mode_children]
    assert any(item.label == "How to Play" for item in view.children)
    assert asyncio.run(view.interaction_check(FakeInteraction("player")))
    assert not asyncio.run(view.interaction_check(FakeInteraction("other")))


def test_how_to_play_is_instructional_view_not_game_mode():
    remembered = []
    view = game_menu.GameModeView(
        player_id="player",
        channel_kind="dm",
        service=object(),
        on_view_changed=remembered.append,
    )
    interaction = FakeInteraction()

    asyncio.run(view.show_how_to_play(interaction))

    content, how_view = interaction.response.edited
    assert isinstance(how_view, game_menu.HowToPlayView)
    assert "How to Play Balloon Frontier" in content
    assert "no special training physics" in content
    assert remembered == [how_view]


def test_selecting_mode_replaces_menu_with_existing_configurator(monkeypatch):
    monkeypatch.setattr(game_menu, "BalloonConfigurator", FakeConfigurator)
    interaction = FakeInteraction()
    finished = []
    view = game_menu.GameModeView(
        player_id="player",
        channel_kind="guild",
        service=object(),
        on_finished=lambda: finished.append(True),
    )

    asyncio.run(view.select_mode(interaction, GameMode.SCENARIO))

    content, configurator = interaction.response.edited
    assert content == "configuration step"
    assert configurator._msg is interaction.message
    assert configurator.service.mode is GameMode.SCENARIO
    assert configurator.service.ui == "discord"
    assert configurator.service.channel_kind == "guild"
    configurator.service.on_finished()
    assert finished == [True]


def test_game_menu_prompt_mentions_how_to_play():
    prompt = game_menu.game_mode_prompt()
    assert "How to Play" in prompt
    assert "Story" in prompt


def test_send_game_menu_resumes_active_view_and_play_can_reset(monkeypatch):
    import discord_bot
    import balloon_frontier.flight_service as flight_service_module

    discord_bot._engaged_players.clear()
    discord_bot._active_views.clear()
    monkeypatch.setattr(flight_service_module, "flight_service", object())
    destination = FakeDestination()

    first = asyncio.run(
        discord_bot.send_game_menu(
            destination,
            player_id="player",
            channel_kind="dm",
        )
    )
    resumed = asyncio.run(
        discord_bot.send_game_menu(
            destination,
            player_id="player",
            channel_kind="dm",
        )
    )
    reset = asyncio.run(
        discord_bot.send_game_menu(
            destination,
            player_id="player",
            channel_kind="dm",
            reset=True,
        )
    )

    assert first is not None
    assert resumed is not None
    assert resumed.view is first.view
    assert reset is not None
    assert reset.view is not first.view
    assert len(destination.sent) == 3

    reset.view.on_finished()
    assert "player" not in discord_bot._engaged_players
    assert "player" not in discord_bot._active_views
