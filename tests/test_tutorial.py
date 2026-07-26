from types import SimpleNamespace

from balloon_frontier.catalog import CATALOG
from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.launch_result import FillMode, LaunchRequest
from balloon_frontier.tutorial import evaluate_tutorial_outcome, tutorial_guidance
from balloon_frontier.tutorial_catalog import ensure_discord_tutorial_options


def _outcome():
    return FlightOutcome(result=SimpleNamespace(peak_altitude_m=0.0, duration_s=0.0))


def _request(*, gas="helium", envelope="mylar", payloads=("quadcopter",), site="field"):
    return LaunchRequest(
        gas_id=gas,
        envelope_id=envelope,
        payload_ids=payloads,
        launch_site_id=site,
        fill_mode=FillMode.AUTO,
    )


def test_quadcopter_is_a_real_shared_catalog_component():
    quadcopter = CATALOG.payload("quadcopter")
    assert quadcopter.name == "Small Quadcopter"
    assert "radio_control" in quadcopter.capabilities


def test_discord_tutorial_exposes_quadcopter_option():
    ensure_discord_tutorial_options()
    from balloon_frontier.discord_ui.configurator import PAYLOAD_OPTIONS

    assert PAYLOAD_OPTIONS["quadcopter"][0] == "Small Quadcopter"


def test_party_balloon_helium_quadcopter_completes_tutorial():
    result = evaluate_tutorial_outcome(_request(), _outcome())

    mission = result.mission_results[0]
    assert mission.completed
    assert "remained controllable" in mission.explanation


def test_hydrogen_is_reported_only_as_observed_loss():
    result = evaluate_tutorial_outcome(_request(gas="hydrogen"), _outcome())

    mission = result.mission_results[0]
    assert not mission.completed
    assert mission.explanation == "The aircraft left communications range and was lost."
    assert "because" not in mission.explanation.lower()


def test_larger_balloon_reports_loss_of_steering_without_tutorial_lecture():
    result = evaluate_tutorial_outcome(_request(envelope="latex"), _outcome())

    mission = result.mission_results[0]
    assert not mission.completed
    assert mission.explanation == "The aircraft could not be steered through the test course."


def test_tutorial_prompts_show_goal_not_answers():
    gas_prompt = tutorial_guidance(0)
    assert "density" in gas_prompt
    assert "Use helium" not in gas_prompt
