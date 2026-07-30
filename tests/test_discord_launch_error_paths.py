import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from balloon_frontier.discord_ui import launch_handler


class _Interaction:
    def __init__(self):
        self.user = SimpleNamespace(id="player")
        self.response = SimpleNamespace(defer=AsyncMock())
        self.edit_original_response = AsyncMock()


class _MalformedConfigurator:
    state = {}


def test_setup_error_after_defer_returns_none_and_renders_failure():
    interaction = _Interaction()

    result = asyncio.run(
        launch_handler.run_launch(
            _MalformedConfigurator(),
            interaction,
            service=object(),
        )
    )

    assert result is None
    interaction.response.defer.assert_awaited_once_with(
        thinking=True,
        ephemeral=False,
    )
    interaction.edit_original_response.assert_awaited_once_with(
        content="❌ The launch simulation failed. Please try again.",
        view=None,
    )
