"""Regression coverage for clear-payload labels and near-ground narratives."""

from balloon_frontier.discord_ui import game_menu
from balloon_frontier.discord_ui.configurator import _Step
from balloon_frontier.discord_ui.views import _OptionButton
from balloon_frontier.game_modes import GameMode
from balloon_frontier.narrative_result import generate_narrative_summary
from balloon_frontier.progression import PlayerRegistry, PlayerState


def _configurator(monkeypatch, mode=GameMode.TUTORIAL):
    player = PlayerState("clear-payload-player")
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
    configurator._current_step = _Step.CHOOSE_PAYLOADS
    configurator.build_buttons()
    return configurator


def test_tutorial_none_option_is_labeled_clear_payloads(monkeypatch):
    configurator = _configurator(monkeypatch)
    labels = [
        item.label
        for item in configurator.children
        if isinstance(item, _OptionButton)
    ]

    assert "Toggle Small Quadcopter" in labels
    assert "Clear payloads" in labels
    assert "Toggle payload 2" not in labels


def test_free_play_payload_buttons_use_names(monkeypatch):
    configurator = _configurator(monkeypatch, GameMode.FREE_PLAY)
    labels = [
        item.label
        for item in configurator.children
        if isinstance(item, _OptionButton)
    ]

    assert "Toggle Camera" in labels
    assert "Clear payloads" in labels


def test_near_ground_short_run_is_not_described_as_climbing():
    narrative = generate_narrative_summary(
        peak_altitude=0.4,
        burst=False,
        landed=False,
        crashed=False,
        time_of_flight=1.0,
    )

    assert "Did not lift off" in narrative
    assert "remained near the launch site" in narrative
    assert "Still climbing slowly" not in narrative
    assert "gaining altitude" not in narrative


def test_meaningful_long_run_keeps_slow_climb_narrative():
    narrative = generate_narrative_summary(
        peak_altitude=100.0,
        burst=False,
        landed=False,
        crashed=False,
        time_of_flight=120.0,
    )

    assert "Still climbing slowly" in narrative
    assert "Did not lift off" not in narrative
