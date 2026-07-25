import pytest

from balloon_frontier.scenarios import ScenarioDefinition, ScenarioSession


class _FakeGameState(dict):
    """A tiny mutable stand-in for the global game state."""


def test_scenario_definition_exists_and_is_constructible():
    sd = ScenarioDefinition(
        scenario_id="s1",
        title="Test Scenario",
        objective_ids=("o1", "o2"),
    )
    assert sd.scenario_id == "s1"
    assert sd.title == "Test Scenario"
    assert sd.objective_ids == ("o1", "o2")


def test_scenario_session_does_not_duplicate_game_state():
    game_state = _FakeGameState(x=1)
    sd = ScenarioDefinition(
        scenario_id="s1",
        title="Test Scenario",
        objective_ids=("o1",),
    )

    session = ScenarioSession(game_state=game_state, definition=sd)

    # Must preserve identity (no deep copy / no re-wrapping).
    assert session.game_state is game_state

    # Mutating the global state should be observable through the session.
    game_state["x"] = 2
    assert session.game_state["x"] == 2


def test_scenario_session_marks_objectives_complete():
    sd = ScenarioDefinition(
        scenario_id="s1",
        title="Test Scenario",
        objective_ids=("o1", "o2"),
    )
    session = ScenarioSession(game_state={}, definition=sd)

    session.mark_objective_complete("o1")
    assert session.is_objective_complete("o1") is True
    assert session.is_objective_complete("o2") is False

    # Marking an unknown objective should be rejected (helps prevent silent typos).
    with pytest.raises(KeyError):
        session.mark_objective_complete("does-not-exist")
