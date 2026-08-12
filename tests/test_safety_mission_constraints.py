"""Mission safety policy remains separate from the physical simulator."""

from balloon_frontier.aerostat import risk_tags_for_request, safety_notes_for_request
from balloon_frontier.launch_result import FillMode, LaunchRequest, MissionAssignment
from balloon_frontier.mission_evaluator import MissionEvaluator
from balloon_frontier.missions import Mission


def _candle_request():
    return LaunchRequest(
        gas_id="air",
        envelope_id="candle_kite",
        payload_ids=("candle_heater",),
        launch_site_id="field",
        fill_mode=FillMode.NORMAL,
    )


def test_safe_configuration_has_no_safety_notes():
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=("camera",),
        launch_site_id="field",
        fill_mode=FillMode.NORMAL,
    )
    assert risk_tags_for_request(request) == frozenset()
    assert safety_notes_for_request(request) == ()


def test_hydrogen_is_reported_as_flammable_without_being_banned_globally():
    request = LaunchRequest(
        gas_id="hydrogen",
        envelope_id="latex",
        payload_ids=(),
        launch_site_id="field",
        fill_mode=FillMode.NORMAL,
    )
    assert "flammable_lifting_gas" in risk_tags_for_request(request)


def test_combined_risk_configuration_reports_each_distinct_risk():
    request = LaunchRequest(
        gas_id="hydrogen",
        envelope_id="candle_kite",
        payload_ids=("candle_heater", "electric_heater"),
        launch_site_id="field",
        fill_mode=FillMode.NORMAL,
    )
    tags = risk_tags_for_request(request)
    assert tags == frozenset(
        {
            "flammable_lifting_gas",
            "heat_sensitive_envelope",
            "open_flame",
            "high_temperature_heat_source",
        }
    )
    notes = safety_notes_for_request(request)
    assert len(notes) == 4
    assert len(set(notes)) == 4


def test_candle_configuration_reports_open_flame_and_envelope_risks():
    request = _candle_request()
    tags = risk_tags_for_request(request)
    notes = safety_notes_for_request(request)
    assert "open_flame" in tags
    assert "heat_sensitive_envelope" in tags
    assert any("Open flame" in note for note in notes)


def test_mission_can_explicitly_prohibit_a_risk_tag():
    mission = Mission(
        id="no_flames",
        title="No Flames",
        description="A mission with an explicit method restriction.",
        launch_site="field",
        budget=100,
        objectives=[],
        prohibited_risk_tags=["open_flame"],
    )
    evaluator = MissionEvaluator({mission.id: mission})
    result = evaluator.evaluate(
        _candle_request(),
        telemetry=(),
        assignment=MissionAssignment((mission.id,), seed=1),
    )[0]

    assert result.completed is False
    assert result.reward == 0
    assert "open_flame" in result.explanation


def test_unrestricted_mission_can_succeed_and_still_report_safety_notes():
    mission = Mission(
        id="experimental",
        title="Experimental Flight",
        description="Judge the outcome, not the method.",
        launch_site="field",
        budget=100,
        objectives=[],
        prohibited_risk_tags=[],
    )
    evaluator = MissionEvaluator({mission.id: mission})
    result = evaluator.evaluate(
        _candle_request(),
        telemetry=(),
        assignment=MissionAssignment((mission.id,), seed=1),
    )[0]

    assert result.completed is True
    assert result.reward == 100
    assert "Safety notes:" in result.explanation
    assert "Open flame" in result.explanation
