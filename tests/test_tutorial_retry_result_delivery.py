"""Regression coverage for successful tutorial retries and result delivery."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from balloon_frontier.discord_ui import launch_handler


def test_continue_view_failure_does_not_turn_success_into_simulation_failure():
    interaction = SimpleNamespace(
        edit_original_response=AsyncMock(side_effect=ValueError("view rejected")),
    )
    continue_view = object()

    asyncio.run(
        launch_handler._attach_tutorial_continue_view(
            interaction,
            continue_view,
        )
    )

    interaction.edit_original_response.assert_awaited_once_with(
        view=continue_view,
    )


def test_no_continue_view_requires_no_discord_edit():
    interaction = SimpleNamespace(edit_original_response=AsyncMock())

    asyncio.run(
        launch_handler._attach_tutorial_continue_view(
            interaction,
            None,
        )
    )

    interaction.edit_original_response.assert_not_awaited()
