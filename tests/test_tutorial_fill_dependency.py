"""Regression coverage for First Flight's dependency-ordered fill step."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from balloon_frontier.discord_ui import game_menu
from balloon_frontier.discord_ui.configurator import _Step
from balloon_frontier.game_modes import GameMode
from balloon_frontier.progression import PlayerRegistry, PlayerState


class _Interaction:
    def __init__(self, user_id="story-player"):
        self.user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(author=self.user)
        self.response = SimpleNamespace(
            edit_message=AsyncMock(),
            send_message=AsyncMock(),
        )


def _configurator(monkeypatch):
    player = PlayerState("story-player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )
    return game_menu._configurator_for_mode(
        service=object(),
        mode=GameMode.STORY,
        player_id="story-player",
        channel_kind="dm",
        on_finished=None,
    )


def test_fill_target_uses_payloads_selected_before_fill(monkeypatch):
    configurator = _configurator(monkeypatch)
    interaction = _Interaction()

    asyncio.run(configurator._on_gas(interaction, 1))
    asyncio.run(configurator._on_envelope(interaction, 1))
    assert configurator._current_step == _Step.CHOOSE_PAYLOADS

    baseline_mass = round(configurator._first_flight_fill_mass("almost_lta"), 3)

    # Parachute is the first optional payload in First Flight.
    asyncio.run(configurator._on_payload(interaction, 1))
    assert "parachute" in configurator.state["payloads"]

    asyncio.run(configurator._advance(interaction))
    assert configurator._current_step == _Step.CHOOSE_SITE
    asyncio.run(configurator._on_site(interaction, 1))
    assert configurator._current_step == _Step.CHOOSE_FILL

    expected_mass = round(configurator._first_flight_fill_mass("almost_lta"), 3)
    assert expected_mass > baseline_mass

    asyncio.run(configurator._on_fill(interaction, 1))
    assert configurator._current_step == _Step.REVIEW_LAUNCH
    assert configurator.state["manual_gas_mass"] == expected_mass
    assert configurator.state["gas_mass"] == expected_mass
    assert "Almost Lighter Than Air" in configurator._step_content()
