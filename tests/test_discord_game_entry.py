import asyncio
from types import SimpleNamespace

from balloon_frontier.game_modes import GameMode
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


def test_mode_menu_lists_every_mode_and_restricts_interactions():
    view = game_menu.GameModeView(
        player_id="player",
        channel_kind="dm",
        service=object(),
    )

    assert [item.mode for item in view.children] == list(GameMode)
    assert asyncio.run(view.interaction_check(FakeInteraction("player")))
    assert not asyncio.run(view.interaction_check(FakeInteraction("other")))


def test_selecting_mode_replaces_menu_with_existing_configurator(monkeypatch):
    monkeypatch.setattr(game_menu, "BalloonConfigurator", FakeConfigurator)
    interaction = FakeInteraction()
    view = game_menu.GameModeView(
        player_id="player",
        channel_kind="guild",
        service=object(),
    )

    asyncio.run(view.select_mode(interaction, GameMode.STORY))

    content, configurator = interaction.response.edited
    assert content == "configuration step"
    assert configurator._msg is interaction.message
    assert configurator.service.mode is GameMode.STORY
    assert configurator.service.ui == "discord"
    assert configurator.service.channel_kind == "guild"


def test_game_menu_prompt_explains_menu_only_flow():
    prompt = game_menu.game_mode_prompt()
    assert "Choose how you want to play" in prompt
    assert "menus and buttons" in prompt


def test_send_game_menu_suppresses_duplicates_and_play_can_reset(monkeypatch):
    import discord_bot
    import balloon_frontier.flight_service as flight_service_module

    discord_bot._engaged_players.clear()
    monkeypatch.setattr(flight_service_module, "flight_service", object())
    destination = FakeDestination()

    first = asyncio.run(
        discord_bot.send_game_menu(
            destination,
            player_id="player",
            channel_kind="dm",
        )
    )
    duplicate = asyncio.run(
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
    assert duplicate is None
    assert reset is not None
    assert len(destination.sent) == 2
