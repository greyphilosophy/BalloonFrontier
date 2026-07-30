"""Regression coverage for resuming the active Discord wizard from chat."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord_bot
from balloon_frontier.discord_ui import launch_handler
from balloon_frontier.discord_ui.game_menu import ContinueToStoryView
from balloon_frontier.discord_ui.modals import _LaunchButton
from balloon_frontier.game_modes import GameMode


class _LiveWizard:
    def __init__(self, content="current wizard step"):
        self.content = content
        self._msg = None
        self.stopped = False

    def _step_content(self):
        return self.content

    def stop(self):
        self.stopped = True


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
    assert not view.stopped


def test_replacing_active_view_retires_superseded_controls():
    first = _LiveWizard("Choose mode")
    second = _LiveWizard("Step 1: Choose gas")

    discord_bot._remember_active_view("player-stale", first)
    discord_bot._remember_active_view("player-stale", second)

    assert first.stopped
    assert not second.stopped
    assert discord_bot._active_views["player-stale"] is second


def test_finish_session_returns_player_to_idle_state():
    view = _LiveWizard()
    discord_bot._remember_active_view("player-3", view)

    discord_bot._finish_session("player-3")

    assert "player-3" not in discord_bot._engaged_players
    assert "player-3" not in discord_bot._active_views


def test_completed_tutorial_updates_resumable_view_without_duplicate_edit(monkeypatch):
    player_id = "tutorial-player"
    context = {
        "mode": GameMode.TUTORIAL,
        "channel_kind": "dm",
        "service": SimpleNamespace(),
        "on_finished": lambda: None,
        "on_view_changed": lambda view: discord_bot._remember_active_view(
            player_id, view
        ),
    }
    parent = SimpleNamespace(_game_entry_context=context)
    button = _LaunchButton(parent, service=SimpleNamespace())
    outcome = SimpleNamespace(
        mission_results=(
            SimpleNamespace(
                mission_id="first_flight",
                completed=True,
            ),
        )
    )
    monkeypatch.setattr(
        launch_handler,
        "run_launch",
        AsyncMock(return_value=outcome),
    )
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=player_id),
        _balloon_frontier_tutorial_view_attached=True,
        edit_original_response=AsyncMock(),
    )

    asyncio.run(button.callback(interaction))

    resumed = discord_bot._active_views[player_id]
    assert isinstance(resumed, ContinueToStoryView)
    assert "Tutorial Complete" in discord_bot._resume_content(resumed)
    interaction.edit_original_response.assert_not_awaited()
