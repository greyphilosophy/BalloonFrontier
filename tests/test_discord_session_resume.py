"""Regression coverage for resuming the active Discord wizard from chat."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord_bot


class _LiveWizard:
    def __init__(self, content="current wizard step"):
        self.content = content
        self._msg = None

    def _step_content(self):
        return self.content


class _Destination:
    def __init__(self):
        self.message = SimpleNamespace(id="resumed-message")
        self.send = AsyncMock(return_value=self.message)


def setup_function():
    discord_bot._engaged_players.clear()
    discord_bot._active_views.clear()


def test_resume_game_resends_current_live_view_and_rebinds_message():
    view = _LiveWizard("Step 4: Choose launch site")
    destination = _Destination()
    discord_bot._remember_active_view("player-1", view)

    result = asyncio.run(
        discord_bot.resume_game(destination, player_id="player-1")
    )

    assert result is destination.message
    destination.send.assert_awaited_once_with(
        "Step 4: Choose launch site",
        view=view,
    )
    assert view._msg is destination.message


def test_resume_game_returns_none_for_idle_player():
    destination = _Destination()

    result = asyncio.run(
        discord_bot.resume_game(destination, player_id="idle-player")
    )

    assert result is None
    destination.send.assert_not_awaited()


def test_send_game_menu_resumes_instead_of_restarting_active_player(monkeypatch):
    view = _LiveWizard("Step 2: Choose envelope")
    destination = _Destination()
    discord_bot._remember_active_view("player-2", view)

    result = asyncio.run(
        discord_bot.send_game_menu(
            destination,
            player_id="player-2",
            channel_kind="dm",
        )
    )

    assert result is destination.message
    destination.send.assert_awaited_once_with(
        "Step 2: Choose envelope",
        view=view,
    )
    assert discord_bot._active_views["player-2"] is view


def test_finish_session_returns_player_to_idle_state():
    view = _LiveWizard()
    discord_bot._remember_active_view("player-3", view)

    discord_bot._finish_session("player-3")

    assert "player-3" not in discord_bot._engaged_players
    assert "player-3" not in discord_bot._active_views
