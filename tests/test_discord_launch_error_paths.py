import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from balloon_frontier.discord_ui import launch_handler


class _Interaction:
    def __init__(self):
        self.user = SimpleNamespace(id="player")
        self.response = SimpleNamespace(defer=AsyncMock())
        self.followup = SimpleNamespace(send=AsyncMock())
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


def test_animation_failure_does_not_discard_successful_flight_results():
    interaction = _Interaction()
    configurator = SimpleNamespace(
        state={
            "gas": "helium",
            "envelope": "latex",
            "site": "field",
            "payloads": ["none"],
            "gas_mass": 0.05,
            "fill_mode": "manual",
            "manual_gas_mass": 0.05,
        }
    )
    telemetry_point = SimpleNamespace(
        time_s=10.0,
        altitude_m=0.0,
        velocity_mps=0.0,
        burst=False,
        landed=True,
        crashed=False,
    )
    result_obj = SimpleNamespace(
        telemetry=(telemetry_point,),
        peak_altitude_m=0.0,
        duration_s=10.0,
        burst=False,
        landed=True,
        crashed=False,
    )
    outcome = SimpleNamespace(
        result=result_obj,
        weather=None,
        mission_assignment=None,
        mission_results=(),
    )
    service = SimpleNamespace(run=lambda request: outcome)

    with patch.object(
        launch_handler,
        "format_discord_results",
        return_value="Flight result",
    ), patch.object(
        launch_handler,
        "chart_to_string",
        return_value="",
    ), patch.object(
        launch_handler.DiscordFlightAnimator,
        "play",
        new=AsyncMock(side_effect=RuntimeError("renderer exploded")),
    ):
        returned = asyncio.run(
            launch_handler.run_launch(configurator, interaction, service)
        )

    assert returned is outcome
    interaction.followup.send.assert_awaited_once_with(content="Flight result")
    interaction.edit_original_response.assert_not_awaited()
