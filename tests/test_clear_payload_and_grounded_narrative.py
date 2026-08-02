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


def test_no_liftoff_replacement_preserves_weather_and_mission_context():
    narrative = generate_narrative_summary(
        peak_altitude=0.4,
        burst=False,
        landed=False,
        crashed=False,
        time_of_flight=1.0,
        weather_briefing="Calm test weather",
        mission_result={
            "missions": [
                {
                    "title": "Ground Test",
                    "is_success": False,
                    "score": 0,
                    "notes": "No sustained climb.",
                }
            ],
            "overall_score": 0,
            "overall_success": False,
            "reputation_gained": 0,
            "budget_earned": 0,
            "player_state": {"reputation": 0, "budget": 100},
            "new_unlocks": [],
        },
    )

    assert "Calm test weather" in narrative
    assert "Did not lift off" in narrative
    assert "Ground Test" in narrative
    assert "Overall Score: 0.0/100" in narrative


def test_altitude_threshold_is_not_classified_as_no_liftoff():
    narrative = generate_narrative_summary(
        peak_altitude=5.0,
        burst=False,
        landed=False,
        crashed=False,
        time_of_flight=1.0,
    )

    assert "Still climbing slowly" in narrative
    assert "Did not lift off" not in narrative


def test_duration_threshold_is_not_classified_as_no_liftoff():
    narrative = generate_narrative_summary(
        peak_altitude=0.4,
        burst=False,
        landed=False,
        crashed=False,
        time_of_flight=10.0,
    )

    assert "Still climbing slowly" in narrative
    assert "Did not lift off" not in narrative


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
