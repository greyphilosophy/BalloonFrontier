from types import SimpleNamespace

from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import MissionResult
from balloon_frontier.session_controller import assign_missions_for_mode, get_mode_policy
from balloon_frontier.story import add_story_bonus_results, story_intro


def _point(*, velocity=2.0, landed=False, crashed=False):
    return SimpleNamespace(velocity_mps=velocity, landed=landed, crashed=crashed)


def _outcome(telemetry):
    return FlightOutcome(
        result=SimpleNamespace(telemetry=tuple(telemetry)),
        mission_results=(
            MissionResult(
                mission_id="edge_of_space",
                completed=True,
                reward=1500,
                explanation="complete",
            ),
        ),
    )


def test_story_mode_assigns_edge_of_space_when_camera_is_selected():
    missions = assign_missions_for_mode(
        GameMode.STORY,
        {"payloads": ("camera",), "site": "field"},
    )
    assert missions == ("edge_of_space",)
    assert get_mode_policy(GameMode.STORY).mission_count == 1


def test_story_intro_separates_tracked_and_future_challenges():
    intro = story_intro()
    assert "Stable footage" in intro
    assert "Controlled recovery" in intro
    assert "Earth and the Moon" in intro
    assert "longest sunset" in intro
    assert "Future cinematic challenges" in intro


def test_story_bonuses_are_derived_from_real_telemetry():
    outcome = add_story_bonus_results(
        _outcome([
            _point(velocity=1.0),
            _point(velocity=2.0),
            _point(velocity=1.5, landed=True),
        ])
    )
    results = {item.mission_id: item for item in outcome.mission_results}
    assert results["bonus_stable_footage"].completed
    assert results["bonus_controlled_recovery"].completed
    assert results["bonus_stable_footage"].reward == 0


def test_unstable_or_crashed_flight_misses_bonuses():
    outcome = add_story_bonus_results(
        _outcome([
            _point(velocity=-20.0),
            _point(velocity=20.0),
            _point(velocity=0.0, landed=True, crashed=True),
        ])
    )
    results = {item.mission_id: item for item in outcome.mission_results}
    assert not results["bonus_stable_footage"].completed
    assert not results["bonus_controlled_recovery"].completed
