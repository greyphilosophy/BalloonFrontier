"""Regression coverage for successful tutorial retries and result delivery."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from balloon_frontier.discord_ui import launch_handler
from balloon_frontier.discord_ui.modals import _LaunchButton
from balloon_frontier.game_modes import GameMode


def test_continue_view_failure_does_not_turn_success_into_simulation_failure():
    interaction = SimpleNamespace(
        edit_original_response=AsyncMock(side_effect=RuntimeError("view rejected")),
    )
    continue_view = object()

    attached = asyncio.run(
        launch_handler._attach_tutorial_continue_view(
            interaction,
            continue_view,
        )
    )

    assert attached is False
    interaction.edit_original_response.assert_awaited_once_with(
        view=continue_view,
    )
    assert not hasattr(
        interaction,
        "_balloon_frontier_tutorial_view_attached",
    )


def test_successful_continue_view_attachment_sets_marker():
    interaction = SimpleNamespace(edit_original_response=AsyncMock())
    continue_view = object()

    attached = asyncio.run(
        launch_handler._attach_tutorial_continue_view(
            interaction,
            continue_view,
        )
    )

    assert attached is True
    assert interaction._balloon_frontier_tutorial_view_attached is True


def test_no_continue_view_requires_no_discord_edit():
    interaction = SimpleNamespace(edit_original_response=AsyncMock())

    attached = asyncio.run(
        launch_handler._attach_tutorial_continue_view(
            interaction,
            None,
        )
    )

    assert attached is False
    interaction.edit_original_response.assert_not_awaited()


def test_result_edit_retries_without_rejected_continue_view():
    interaction = SimpleNamespace(
        edit_original_response=AsyncMock(
            side_effect=[RuntimeError("view rejected"), None],
        )
    )
    continue_view = object()

    asyncio.run(
        launch_handler._edit_results_with_optional_view(
            interaction,
            "successful flight report",
            continue_view,
        )
    )

    assert interaction.edit_original_response.await_args_list == [
        (( ), {"content": "successful flight report", "view": continue_view}),
        (( ), {"content": "successful flight report", "view": None}),
    ]


def test_tutorial_continue_view_registers_the_exact_created_view(monkeypatch):
    created_view = object()
    constructor = Mock(return_value=created_view)
    remembered = []

    from balloon_frontier.discord_ui import game_menu

    monkeypatch.setattr(game_menu, "ContinueToStoryView", constructor)
    configurator = SimpleNamespace(
        _game_entry_context={
            "mode": GameMode.TUTORIAL,
            "channel_kind": "dm",
            "service": "root-service",
            "on_finished": None,
            "on_view_changed": remembered.append,
        }
    )
    interaction = SimpleNamespace(user=SimpleNamespace(id="player"))
    result = SimpleNamespace(
        mission_results=(
            SimpleNamespace(mission_id="first_flight", completed=True),
        )
    )

    view = launch_handler._tutorial_continue_view(
        configurator,
        interaction,
        result,
    )

    assert view is created_view
    assert remembered == [created_view]
    assert interaction._balloon_frontier_tutorial_continuation_handled is True
    constructor.assert_called_once_with(
        player_id="player",
        channel_kind="dm",
        service="root-service",
        on_finished=None,
        on_view_changed=remembered.append,
    )


def test_launch_button_skips_legacy_fallback_when_handler_owned_continuation(monkeypatch):
    outcome = SimpleNamespace(
        mission_results=(
            SimpleNamespace(mission_id="first_flight", completed=True),
        )
    )

    async def run_launch(parent, interaction, service):
        interaction._balloon_frontier_tutorial_continuation_handled = True
        return outcome

    monkeypatch.setattr(launch_handler, "run_launch", run_launch)
    parent = SimpleNamespace(
        _game_entry_context={
            "mode": GameMode.TUTORIAL,
            "channel_kind": "dm",
            "service": "root-service",
        }
    )
    interaction = SimpleNamespace(
        user=SimpleNamespace(id="player"),
        edit_original_response=AsyncMock(),
    )
    button = _LaunchButton(parent, service="wrapped-service")

    asyncio.run(button.callback(interaction))

    interaction.edit_original_response.assert_not_awaited()
