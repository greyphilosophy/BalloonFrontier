"""Discord payload toggles should identify both the action and resulting loadout."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from balloon_frontier.career_prologue import DiscoveryFirstFlightConfiguratorMixin
from balloon_frontier.discord_ui import game_menu
from balloon_frontier.discord_ui.configurator import _Step
from balloon_frontier.discord_ui.payload_feedback import PayloadFeedbackConfiguratorMixin
from balloon_frontier.game_modes import GameMode
from balloon_frontier.progression import PlayerRegistry, PlayerState


def _configurator(monkeypatch, mode=GameMode.STORY):
    player = PlayerState("payload-feedback-player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )
    configurator = game_menu._configurator_for_mode(
        service=object(),
        mode=mode,
        player_id=player.player_id,
        channel_kind="dm",
        on_finished=None,
    )
    assert isinstance(configurator, PayloadFeedbackConfiguratorMixin)
    if mode in (GameMode.STORY, GameMode.TUTORIAL):
        assert isinstance(configurator, DiscoveryFirstFlightConfiguratorMixin)
        assert configurator._game_entry_context["mode"] is GameMode.STORY
    configurator._current_step = _Step.CHOOSE_PAYLOADS
    configurator.state["payloads"] = ["none"]
    configurator.build_buttons()
    return configurator


def _interaction():
    return SimpleNamespace(
        message=SimpleNamespace(),
        response=SimpleNamespace(
            edit_message=AsyncMock(),
            send_message=AsyncMock(),
        ),
    )


def test_adding_first_flight_payload_edits_message_with_direct_feedback(monkeypatch):
    configurator = _configurator(monkeypatch)
    interaction = _interaction()

    asyncio.run(configurator._on_payload(interaction, 1))

    assert configurator.state["payloads"] == ["camera"]
    content = interaction.response.edit_message.await_args.kwargs["content"]
    assert "✅ **Added:** Camera" in content
    assert "**Currently equipped:** Camera" in content


def test_removing_last_payload_edits_message_with_empty_loadout(monkeypatch):
    configurator = _configurator(monkeypatch)
    configurator.state["payloads"] = ["camera"]
    interaction = _interaction()

    asyncio.run(configurator._on_payload(interaction, 1))

    assert configurator.state["payloads"] == ["none"]
    content = interaction.response.edit_message.await_args.kwargs["content"]
    assert "➖ **Removed:** Camera" in content
    assert "**Currently equipped:** None" in content


def test_legacy_tutorial_alias_receives_story_first_flight_feedback(monkeypatch):
    configurator = _configurator(monkeypatch, GameMode.TUTORIAL)
    interaction = _interaction()

    asyncio.run(configurator._on_payload(interaction, 2))

    content = interaction.response.edit_message.await_args.kwargs["content"]
    assert configurator.state["payloads"] == ["parachute"]
    assert "✅ **Added:** Parachute" in content
    assert "**Currently equipped:** Parachute" in content


def test_free_play_payload_toggle_receives_direct_feedback(monkeypatch):
    configurator = _configurator(monkeypatch, GameMode.FREE_PLAY)
    interaction = _interaction()

    asyncio.run(configurator._on_payload(interaction, 1))

    content = interaction.response.edit_message.await_args.kwargs["content"]
    assert "✅ **Added:** Camera" in content
    assert "**Currently equipped:** Camera" in content


def test_toggle_action_feedback_does_not_reappear_after_navigation(monkeypatch):
    configurator = _configurator(monkeypatch)
    interaction = _interaction()
    asyncio.run(configurator._on_payload(interaction, 1))
    assert "✅ **Added:** Camera" in configurator._step_content()

    asyncio.run(configurator._advance(interaction))
    assert configurator._current_step == _Step.CHOOSE_SITE
    configurator._prev_step()

    content = configurator._step_content()
    assert "✅ **Added:** Camera" not in content
    assert "**Currently equipped:** Camera" in content
