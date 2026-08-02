"""Story starts with first flight without presenting it as a tutorial."""

from dataclasses import dataclass

from balloon_frontier.balloon_cluster import BalloonClusterFlightService
from balloon_frontier.career_prologue import (
    DiscoveryFirstFlightConfiguratorMixin,
    DiscoveryFirstFlightService,
    discovery_first_flight_outcome,
)
from balloon_frontier.discord_ui import game_menu
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import MissionResult
from balloon_frontier.progression import PlayerRegistry, PlayerState
from balloon_frontier.session_controller import plan_session


@dataclass(frozen=True)
class _Outcome:
    mission_results: tuple[MissionResult, ...]


def _configuration():
    return {
        "gas": "helium",
        "envelope": "mylar",
        "fill_mode": "auto",
        "payloads": ("quadcopter",),
        "site": "field",
    }


def test_new_discord_story_player_gets_first_flight_session(monkeypatch):
    player = PlayerState("new-player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )

    plan = plan_session(
        GameMode.STORY,
        _configuration(),
        player_id="new-player",
        context={"ui": "discord"},
    )

    assert plan.session.mode is GameMode.TUTORIAL
    assert plan.missions == ("first_flight",)
    assert dict(plan.context) == {"ui": "discord"}


def test_exploratory_story_choice_still_assigns_first_flight(monkeypatch):
    player = PlayerState("new-player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )
    configuration = {
        **_configuration(),
        "payloads": ("none",),
    }

    plan = plan_session(
        GameMode.STORY,
        configuration,
        player_id="new-player",
        context={"ui": "discord"},
    )

    assert plan.session.mode is GameMode.TUTORIAL
    assert plan.missions == ("first_flight",)


def test_new_non_discord_story_player_keeps_normal_story(monkeypatch):
    player = PlayerState("new-player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )

    plan = plan_session(
        GameMode.STORY,
        _configuration(),
        player_id="new-player",
        context={"ui": "cli"},
    )

    assert plan.session.mode is GameMode.STORY
    assert plan.missions == ("edge_of_space",)
    assert dict(plan.context) == {"ui": "cli"}


def test_completed_player_starts_normal_story(monkeypatch):
    player = PlayerState("returning-player")
    player.missions_completed.append("first_flight")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )

    plan = plan_session(
        GameMode.STORY,
        _configuration(),
        player_id="returning-player",
        context={"ui": "discord"},
    )

    assert plan.session.mode is GameMode.STORY
    assert plan.missions == ("edge_of_space",)


def test_discord_story_prologue_hides_tutorial_signposting(monkeypatch):
    player = PlayerState("new-player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )

    configurator = game_menu._configurator_for_mode(
        service=object(),
        mode=GameMode.STORY,
        player_id="new-player",
        channel_kind="dm",
        on_finished=None,
    )

    assert isinstance(configurator, DiscoveryFirstFlightConfiguratorMixin)
    assert isinstance(configurator._service, BalloonClusterFlightService)
    assert isinstance(configurator._service.service, DiscoveryFirstFlightService)
    content = configurator._step_content()
    assert "Your First Flight" in content
    assert "Tutorial" not in content
    assert "Green buttons" not in content
    assert all(item.style.name != "success" for item in configurator.children)

    context = configurator._game_entry_context
    assert context["requested_mode"] is GameMode.STORY
    assert context["mode"] is GameMode.TUTORIAL
    assert context["hidden_story_prologue"] is True


def test_first_flight_handoff_uses_career_neutral_copy():
    view = game_menu.ContinueToStoryView(
        player_id="new-player",
        channel_kind="dm",
        service=object(),
    )

    assert "First Flight Complete" in view._resume_content
    assert "Tutorial" not in view._resume_content
    assert view.children[0].label == "Continue Career"


def test_hidden_prologue_debrief_does_not_reference_guided_choices():
    outcome = _Outcome(
        mission_results=(
            MissionResult(
                mission_id="first_flight",
                completed=False,
                reward=0,
                explanation=(
                    "**Try next**\n- Follow the green recommended choices and launch again."
                ),
            ),
        )
    )

    rewritten = discovery_first_flight_outcome(outcome)
    result = rewritten.mission_results[0]

    assert result.completed is False
    assert result.reward == 0
    assert "green" not in result.explanation.lower()
    assert "recommended choices" not in result.explanation.lower()
    assert "different combination" in result.explanation


def test_hidden_prologue_success_keeps_reward_with_discovery_wording():
    outcome = _Outcome(
        mission_results=(
            MissionResult(
                mission_id="first_flight",
                completed=True,
                reward=500,
                explanation=(
                    "**Why**\n- The recommended gas, assist envelope, fill, and "
                    "active control worked together."
                ),
            ),
        )
    )

    rewritten = discovery_first_flight_outcome(outcome)
    result = rewritten.mission_results[0]

    assert result.completed is True
    assert result.reward == 500
    assert "recommended gas" not in result.explanation
    assert "Your gas, envelope, fill, and active-control choices" in result.explanation
