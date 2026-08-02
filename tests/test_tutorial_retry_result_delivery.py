"""Regression coverage for successful tutorial retries and result delivery."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

from balloon_frontier.discord_ui import launch_handler
from balloon_frontier.discord_ui.modals import _LaunchButton
from balloon_frontier.game_modes import GameMode


class _SlottedInteraction:
    """Discord-like interaction that rejects arbitrary application attributes."""

    __slots__ = ("user", "edit_original_response", "followup")

    def __init__(self, *, followup=None):
        self.user = SimpleNamespace(id="player")
        self.edit_original_response = AsyncMock()
        self.followup = followup


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


def test_successful_continue_view_attachment_does_not_mutate_interaction():
    interaction = _SlottedInteraction()
    continue_view = object()

    attached = asyncio.run(
        launch_handler._attach_tutorial_continue_view(
            interaction,
            continue_view,
        )
    )

    assert attached is True
    interaction.edit_original_response.assert_awaited_once_with(view=continue_view)


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
        call(content="successful flight report", view=continue_view),
        call(content="successful flight report", view=None),
    ]


def test_followup_failure_falls_back_to_original_response():
    followup = SimpleNamespace(
        send=AsyncMock(side_effect=RuntimeError("webhook expired")),
    )
    interaction = _SlottedInteraction(followup=followup)

    delivered = asyncio.run(
        launch_handler._send_results(interaction, "completed flight report")
    )

    assert delivered is True
    followup.send.assert_awaited_once_with(content="completed flight report")
    interaction.edit_original_response.assert_awaited_once_with(
        content="completed flight report",
        view=None,
    )


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
    interaction = _SlottedInteraction()
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
    assert configurator._tutorial_continuation_handled is True
    constructor.assert_called_once_with(
        player_id="player",
        channel_kind="dm",
        service="root-service",
        on_finished=None,
        on_view_changed=remembered.append,
    )


def test_failed_continue_view_construction_leaves_fallback_available(monkeypatch):
    from balloon_frontier.discord_ui import game_menu

    monkeypatch.setattr(
        game_menu,
        "ContinueToStoryView",
        Mock(side_effect=RuntimeError("constructor failed")),
    )
    configurator = SimpleNamespace(
        _game_entry_context={
            "mode": GameMode.TUTORIAL,
            "channel_kind": "dm",
            "service": "root-service",
            "on_finished": None,
        }
    )
    interaction = _SlottedInteraction()
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

    assert view is None
    assert not hasattr(configurator, "_tutorial_continuation_handled")


def test_registry_failure_does_not_discard_created_continue_view(monkeypatch):
    created_view = object()
    constructor = Mock(return_value=created_view)

    from balloon_frontier.discord_ui import game_menu

    monkeypatch.setattr(game_menu, "ContinueToStoryView", constructor)

    def reject_registration(view):
        raise RuntimeError("registry unavailable")

    configurator = SimpleNamespace(
        _game_entry_context={
            "mode": GameMode.TUTORIAL,
            "channel_kind": "dm",
            "service": "root-service",
            "on_finished": None,
            "on_view_changed": reject_registration,
        }
    )
    interaction = _SlottedInteraction()
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
    assert configurator._tutorial_continuation_handled is True


def test_terminal_status_edit_failure_is_contained():
    interaction = SimpleNamespace(
        edit_original_response=AsyncMock(
            side_effect=RuntimeError("interaction expired")
        )
    )

    edited = asyncio.run(
        launch_handler._safe_edit_original_response(
            interaction,
            content="status",
            view=None,
        )
    )

    assert edited is False
    interaction.edit_original_response.assert_awaited_once_with(
        content="status",
        view=None,
    )


def test_launch_button_skips_legacy_fallback_when_handler_owned_continuation(
    monkeypatch,
):
    outcome = SimpleNamespace(
        mission_results=(
            SimpleNamespace(mission_id="first_flight", completed=True),
        )
    )

    async def run_launch(parent, interaction, service):
        parent._tutorial_continuation_handled = True
        return outcome

    monkeypatch.setattr(launch_handler, "run_launch", run_launch)
    parent = SimpleNamespace(
        _game_entry_context={
            "mode": GameMode.TUTORIAL,
            "channel_kind": "dm",
            "service": "root-service",
        }
    )
    interaction = _SlottedInteraction()
    button = _LaunchButton(parent, service="wrapped-service")

    asyncio.run(button.callback(interaction))

    interaction.edit_original_response.assert_not_awaited()
