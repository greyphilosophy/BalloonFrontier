"""Regression tests proving tutorial outcomes follow observed telemetry."""

from types import SimpleNamespace

from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.tutorial import evaluate_tutorial_outcome


def _request(*, gas="helium"):
    return SimpleNamespace(
        gas_id=gas,
        envelope_id="mylar",
        fill_mode=SimpleNamespace(value="auto"),
        payload_ids=("quadcopter",),
        launch_site_id="field",
        balloon_count=1,
    )


def _outcome(*, burst=False, landed=False, crashed=False):
    return FlightOutcome(
        result=SimpleNamespace(
            peak_altitude_m=250.0,
            duration_s=90.0,
            burst=burst,
            landed=landed,
            crashed=crashed,
        )
    )


def test_unconfirmed_recovery_fails_endurance_course_without_inventing_cause():
    mission = evaluate_tutorial_outcome(_request(), _outcome()).mission_results[0]

    assert not mission.completed
    assert mission.reward == 0
    assert "still airborne" in mission.explanation
    assert "cannot identify a specific control failure" in mission.explanation


def test_confirmed_recovery_completes_recommended_route():
    mission = evaluate_tutorial_outcome(
        _request(),
        _outcome(landed=True),
    ).mission_results[0]

    assert mission.completed
    assert mission.reward == 500
    assert "landed successfully" in mission.explanation


def test_recommended_design_cannot_pass_after_burst_even_if_it_lands():
    mission = evaluate_tutorial_outcome(
        _request(),
        _outcome(burst=True, landed=True),
    ).mission_results[0]

    assert not mission.completed
    assert mission.reward == 0
    assert "The balloon burst" in mission.explanation
    assert "The aircraft landed successfully" in mission.explanation


def test_safe_hot_air_flight_reports_tradeoff_without_inventing_failure_events():
    mission = evaluate_tutorial_outcome(
        _request(gas="hot_air"),
        _outcome(landed=True),
    ).mission_results[0]

    assert not mission.completed
    assert mission.reward == 0
    assert "The aircraft landed successfully" in mission.explanation
    assert "Hot air offers less lift and endurance" in mission.explanation
    assert "crashed" not in mission.explanation.lower()
    assert "burst" not in mission.explanation.lower()
