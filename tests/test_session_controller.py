from dataclasses import dataclass

import pytest

from balloon_frontier.game_modes import GameMode
from balloon_frontier.game_session import SessionState
from balloon_frontier import session_controller as controller


@dataclass
class StubMission:
    required_payloads: tuple[str, ...] = ()
    launch_site: str | None = None


def test_playable_modes_have_explicit_policies_and_tutorial_is_story_alias():
    assert controller.get_mode_policy(GameMode.TUTORIAL) == controller.get_mode_policy(
        GameMode.STORY
    )
    assert controller.get_mode_policy(GameMode.STORY).uses_progression
    assert controller.get_mode_policy(GameMode.STORY).mission_count == 1
    assert controller.get_mode_policy(GameMode.SCENARIO).mission_count == 3
    assert controller.get_mode_policy(GameMode.FREE_PLAY).sandbox
    assert not controller.get_mode_policy(GameMode.FREE_PLAY).requires_missions


def test_free_play_assigns_no_missions(monkeypatch):
    monkeypatch.setattr(controller, "ensure_missions_loaded", lambda mission_dir=None: None)
    assert controller.assign_missions_for_mode(
        GameMode.FREE_PLAY,
        {"payloads": ["camera"], "site": "field"},
    ) == ()


def test_legacy_tutorial_alias_uses_story_first_flight(monkeypatch):
    monkeypatch.setattr(controller, "ensure_missions_loaded", lambda mission_dir=None: None)
    monkeypatch.setitem(controller.MISSIONS, "first_flight", StubMission())
    missions = controller.assign_missions_for_mode(
        GameMode.TUTORIAL,
        {"payloads": ["none"], "site": "field"},
    )
    assert missions == ("first_flight",)


def test_story_uses_chapter_and_scenario_remains_deterministic(monkeypatch):
    monkeypatch.setattr(controller, "ensure_missions_loaded", lambda mission_dir=None: None)
    monkeypatch.setitem(controller.MISSIONS, "first_flight", StubMission())
    seen = []

    def fake_select_missions(**kwargs):
        seen.append(kwargs)
        return [f"mission-{kwargs['seed']}-{i}" for i in range(kwargs["mission_count"])]

    monkeypatch.setattr(controller, "select_missions", fake_select_missions)
    configuration = {"gas": "helium", "payloads": ["camera"], "site": "field"}

    first = controller.assign_missions_for_mode("story", configuration)
    second = controller.assign_missions_for_mode("story", configuration)
    scenario_one = controller.assign_missions_for_mode(
        "scenario", configuration, context={"chapter": 2}
    )
    scenario_two = controller.assign_missions_for_mode(
        "scenario", configuration, context={"chapter": 2}
    )

    assert first == second == ("first_flight",)
    assert scenario_one == scenario_two
    assert seen[0]["seed"] == seen[1]["seed"]
    assert len(scenario_one) == 3
    assert first != scenario_one


def test_scenario_keeps_empty_assignment_when_no_missions_are_compatible(monkeypatch):
    monkeypatch.setattr(controller, "ensure_missions_loaded", lambda mission_dir=None: None)
    seen = []

    def no_compatible_missions(**kwargs):
        seen.append(kwargs)
        return []

    monkeypatch.setattr(controller, "select_missions", no_compatible_missions)

    missions = controller.assign_missions_for_mode(
        GameMode.SCENARIO,
        {"payloads": ["camera"], "site": "rooftop"},
    )

    assert missions == ()
    assert seen == [
        {
            "mission_count": 3,
            "seed": seen[0]["seed"],
            "selected_payloads": ["camera"],
            "launch_site": "rooftop",
            "mission_dir": None,
        }
    ]


def test_scenario_strips_none_payload_before_compatibility_filtering(monkeypatch):
    monkeypatch.setattr(controller, "ensure_missions_loaded", lambda mission_dir=None: None)
    captured = {}

    def capture_selection(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(controller, "select_missions", capture_selection)

    missions = controller.assign_missions_for_mode(
        "scenario",
        {"payloads": ["none"], "launch_site": "mountain"},
    )

    assert missions == ()
    assert captured["selected_payloads"] == []
    assert captured["launch_site"] == "mountain"


def test_scenario_does_not_mutate_configuration_or_context(monkeypatch):
    monkeypatch.setattr(controller, "ensure_missions_loaded", lambda mission_dir=None: None)
    monkeypatch.setattr(controller, "select_missions", lambda **kwargs: [])
    configuration = {"payloads": ["camera", "none"], "site": "field"}
    context = {"difficulty": "hard", "attempt": 2}

    controller.assign_missions_for_mode(
        GameMode.SCENARIO,
        configuration,
        context=context,
    )

    assert configuration == {"payloads": ["camera", "none"], "site": "field"}
    assert context == {"difficulty": "hard", "attempt": 2}


def test_scenario_forwards_custom_mission_directory(monkeypatch):
    loaded = []
    selected = []
    monkeypatch.setattr(
        controller,
        "ensure_missions_loaded",
        lambda mission_dir=None: loaded.append(mission_dir),
    )

    def capture_selection(**kwargs):
        selected.append(kwargs)
        return []

    monkeypatch.setattr(controller, "select_missions", capture_selection)

    missions = controller.assign_missions_for_mode(
        GameMode.SCENARIO,
        {"payloads": [], "site": "field"},
        mission_dir="tests/fixtures/no-compatible-scenarios",
    )

    assert missions == ()
    assert loaded == ["tests/fixtures/no-compatible-scenarios"]
    assert selected[0]["mission_dir"] == "tests/fixtures/no-compatible-scenarios"


def test_plan_session_is_ready_and_legacy_tutorial_normalizes_to_story(monkeypatch):
    monkeypatch.setattr(
        controller,
        "assign_missions_for_mode",
        lambda *args, **kwargs: ("m1",),
    )
    plan = controller.plan_session(
        "tutorial",
        {"gas": "helium", "payloads": ["camera"], "site": "field"},
        player_id="player-1",
        context={"source": "cli"},
    )
    assert plan.session.state is SessionState.READY
    assert plan.session.mode is GameMode.STORY
    assert plan.session.player_id == "player-1"
    assert plan.missions == ("m1",)
    assert plan.context["source"] == "cli"
    with pytest.raises(TypeError):
        plan.context["source"] = "discord"


def test_registry_isolates_players_and_cancels_interrupted_sessions(monkeypatch):
    monkeypatch.setattr(controller, "assign_missions_for_mode", lambda *args, **kwargs: ())
    registry = controller.SessionRegistry()
    alice = controller.plan_session("free play", {"gas": "helium"}, player_id="alice")
    bob = controller.plan_session("free play", {"gas": "hydrogen"}, player_id="bob")
    registry.put("alice", alice)
    registry.put("bob", bob)
    assert registry.get("alice") is alice
    assert registry.get("bob") is bob
    assert registry.cancel("alice")
    assert alice.session.state is SessionState.CANCELLED
    assert registry.get("bob") is bob
    assert not registry.cancel("missing")


def test_cli_and_discord_contexts_share_core_outcome(monkeypatch):
    monkeypatch.setattr(
        controller,
        "assign_missions_for_mode",
        lambda *args, **kwargs: ("shared",),
    )
    configuration = {"gas": "helium", "payloads": ["camera"], "site": "field"}
    cli = controller.plan_session(
        "scenario", configuration, player_id="p", context={"ui": "cli"}
    )
    discord = controller.plan_session(
        "scenario", configuration, player_id="p", context={"ui": "discord"}
    )
    assert cli.session.mode is discord.session.mode
    assert cli.session.configuration == discord.session.configuration
    assert cli.policy == discord.policy
    assert cli.missions == discord.missions
