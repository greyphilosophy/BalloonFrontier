"""Payload toggles visibly confirm the current hidden-prologue loadout."""

from balloon_frontier.career_prologue import DiscoveryFirstFlightConfiguratorMixin
from balloon_frontier.discord_ui import game_menu
from balloon_frontier.discord_ui.configurator import _Step
from balloon_frontier.game_modes import GameMode
from balloon_frontier.progression import PlayerRegistry, PlayerState


def _configurator(monkeypatch):
    player = PlayerState("payload-player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )
    configurator = game_menu._configurator_for_mode(
        service=object(),
        mode=GameMode.STORY,
        player_id="payload-player",
        channel_kind="dm",
        on_finished=None,
    )
    assert isinstance(configurator, DiscoveryFirstFlightConfiguratorMixin)
    configurator._current_step = _Step.CHOOSE_PAYLOADS
    return configurator


def test_payload_step_shows_none_when_nothing_is_equipped(monkeypatch):
    configurator = _configurator(monkeypatch)
    configurator.state["payloads"] = ["none"]

    content = configurator._step_content()

    assert "**Currently equipped:** None" in content


def test_payload_step_lists_equipped_items_in_menu_order(monkeypatch):
    configurator = _configurator(monkeypatch)
    configurator.state["payloads"] = ["quadcopter", "camera"]

    content = configurator._step_content()

    assert "**Currently equipped:** Camera, Small Quadcopter" in content
