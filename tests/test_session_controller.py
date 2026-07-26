from dataclasses import dataclass

import pytest

from balloon_frontier.game_modes import GameMode
from balloon_frontier.game_session import SessionState
from balloon_frontier import session_controller as controller


@dataclass
class StubMission:
    required_payloads: tuple[str, ...] = ()
    launch_site: str | None = None


def test_every_mode_has_explicit_distinct_policy():
    policies = {mode: controller.get_mode_policy(mode) for mode in GameMode}

    assert policies[GameMode.TUTORIAL].mission_count == 1
    assert policies[GameMode.STORY].uses_progression
    assert policies[GameMode.STORY].mission_count == 1
    assert policies[GameMode.SCENARIO].mission_count == 3
    assert policies[GameMode.FREE_PLAY].sandbox
    assert not policies[GameMode.FREE_PLAY].requires_missions


def test_free_play_assigns_no_missions(monkeypatch):
    monkeypatch.setattr(controller, "ensure_missions_loaded", lambda mission_dir=None: None)
    assert controller.assign_missions_for_mode(
        GameMode.FREE_PLAY,
        {"payloads": ["camera"], "site": "field"},
    ) == ()


def test_tutorial_prefers_compatible_first_flight(monkeypatch):
    monkeypatch.setattr(controller, "ensure_missions_loaded", lambda mission_dir=None: None)
    monkeypatch.setitem(controller.MISSIONS, "first_flight", StubMission())

    missions = controller.assign_missions_for_mode(
        GameMode.TUTORIAL,
        {"payloads": ["none"], "site": "field"},
    )

    assert missions == ("first_flight",)


def test_story_and_scenario_assignment_is_deterministic(monkeypatch):
    monkeypatch.setattr(controller, "ensure_missions_loaded", lambda mission_dir=None: None)
    seen = []

    def fake_select_missions(**kwargs):
        seen.append(kwargs)
        return [f"mission-{kwargs['seed']}-{i}" for i in range(kwargs["mission_count"])]

    monkeypatch.setattr(controller, "select_missions", fake_select_missions)
    configuration = {"gas": "helium", "payloads": ["camera"], "site": "field"}

    first = controller.assign_missions_for_mode("story", configuration, context={"chapter": 2})
    second = controller.assign_missions_for_mode("story", configuration, context={"chapter": 2})
    scenario = controller.assign_missions_for_mode("scenario", configuration, context={"chapter": 2})

    assert first == second
    assert seen[0]["seed"] == seen[1]["seed"]
    assert len(first) == 1
    assert len(scenario) == 3
    assert first != scenario


def test_plan_session_is_ready_and_ui_agnostic(monkeypatch):
    monkeypatch.setattr(controller, "assign_missions_for_mode", lambda *args, **kwargs: ("m1",))

    plan = controller.plan_session(
        "tutorial",
        {"gas": "helium", "payloads": ["camera"], "site": "field"},
        player_id="player-1",
        context={"source": "cli"},
    )

    assert plan.session.state is SessionState.READY
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
    monkeypatch.setattr(controller, "assign_missions_for_mode", lambda *args, **kwargs: ("shared",))
    configuration = {"gas": "helium", "payloads": ["camera"], "site": "field"}

    cli = controller.plan_session("scenario", configuration, player_id="p", context={"ui": "cli"})
    discord = controller.plan_session("scenario", configuration, player_id="p", context={"ui": "discord"})

    assert cli.session.mode is discord.session.mode
    assert cli.session.configuration == discord.session.configuration
    assert cli.policy == discord.policy
    assert cli.missions == discord.missions
