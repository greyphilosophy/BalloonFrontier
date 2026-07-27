"""End-to-end coverage for the guided Discord tutorial journey."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from balloon_frontier.discord_ui.configurator import (
    BalloonConfigurator,
    PAYLOAD_OPTIONS,
    _Step,
)
from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.launch_result import FillMode, LaunchRequest
from balloon_frontier.progression import PlayerRegistry, PlayerState
from balloon_frontier.tutorial import (
    TutorialConfiguratorMixin,
    evaluate_tutorial_outcome,
)
from balloon_frontier.tutorial_catalog import ensure_discord_tutorial_options


class _Interaction:
    def __init__(self, user_id="tutorial-player"):
        self.user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(author=self.user)
        self.response = SimpleNamespace(
            edit_message=AsyncMock(),
            send_message=AsyncMock(),
        )


def _tutorial_configurator():
    ensure_discord_tutorial_options()
    tutorial_type = type(
        "TutorialBalloonConfigurator",
        (TutorialConfiguratorMixin, BalloonConfigurator),
        {},
    )
    return tutorial_type(service=SimpleNamespace())


def _outcome():
    return FlightOutcome(
        result=SimpleNamespace(peak_altitude_m=0.0, duration_s=0.0),
    )


def _request_from(configurator, player_id="tutorial-player"):
    state = configurator.state
    return LaunchRequest(
        gas_id=state["gas"],
        envelope_id=state["envelope"],
        payload_ids=tuple(state["payloads"]),
        launch_site_id=state["site"],
        fill_mode=FillMode(state["fill_mode"]),
        manual_gas_mass_kg=state["manual_gas_mass"],
        player_id=player_id,
    )


async def _drive_tutorial_route(configurator, interaction, *, gas_index):
    await configurator._on_gas(interaction, gas_index)
    await configurator._on_envelope(interaction, 1)  # mylar
    await configurator._on_fill(interaction, 1)  # automatic fill

    quadcopter_index = list(PAYLOAD_OPTIONS).index("quadcopter") + 1
    await configurator._on_payload(interaction, quadcopter_index)
    await configurator._advance(interaction)
    await configurator._on_site(interaction, 1)  # open field


def test_new_player_can_complete_recommended_tutorial_route(monkeypatch):
    """Exercise every guided configurator step through the final outcome."""
    new_player = PlayerState("tutorial-player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: new_player),
    )

    configurator = _tutorial_configurator()
    interaction = _Interaction()

    assert configurator._current_step == _Step.CHOOSE_GAS
    asyncio.run(
        _drive_tutorial_route(
            configurator,
            interaction,
            gas_index=1,
        )
    )

    assert configurator._current_step == _Step.REVIEW_LAUNCH
    assert configurator.state["gas"] == "helium"
    assert configurator.state["envelope"] == "mylar"
    assert configurator.state["payloads"] == ["quadcopter"]
    assert configurator.state["site"] == "field"
    assert "Review and launch" in configurator._step_content()

    result = evaluate_tutorial_outcome(_request_from(configurator), _outcome())
    mission = result.mission_results[0]

    assert mission.completed
    assert mission.reward == 500
    assert "remained controllable" in mission.explanation
    interaction.response.send_message.assert_not_awaited()


def test_tutorial_alternative_route_reaches_failure_result(monkeypatch):
    """Alternative choices remain usable and teach through the final result."""
    new_player = PlayerState("tutorial-player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: new_player),
    )

    configurator = _tutorial_configurator()
    interaction = _Interaction()

    asyncio.run(
        _drive_tutorial_route(
            configurator,
            interaction,
            gas_index=2,
        )
    )

    mission = evaluate_tutorial_outcome(
        _request_from(configurator),
        _outcome(),
    ).mission_results[0]

    assert not mission.completed
    assert mission.reward == 0
    assert mission.explanation == "The aircraft left communications range and was lost."
