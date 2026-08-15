"""Story starts with a small first flight without a separate tutorial mode."""

from balloon_frontier.balloon_cluster import BalloonClusterFlightService
from balloon_frontier.career_prologue import DiscoveryFirstFlightConfiguratorMixin
from balloon_frontier.discord_ui import game_menu
from balloon_frontier.game_modes import GameMode
from balloon_frontier.progression import PlayerRegistry, PlayerState
from balloon_frontier.session_adapters import SessionAwareFlightService
from balloon_frontier.session_controller import plan_session
from balloon_frontier.story import (
    EDGE_OF_SPACE_MISSION_ID,
    FIRST_FLIGHT_MISSION_ID,
    current_story_chapter,
)


def _configuration():
    return {
        "gas": "helium",
        "envelope": "latex",
        "fill_mode": "auto",
        "payloads": ("camera",),
        "site": "field",
    }


def test_new_story_player_gets_first_flight_without_mode_substitution(monkeypatch):
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

    assert plan.session.mode is GameMode.STORY
    assert plan.missions == (FIRST_FLIGHT_MISSION_ID,)
    assert dict(plan.context) == {"ui": "discord"}


def test_legacy_tutorial_request_normalizes_to_same_story_plan(monkeypatch):
    player = PlayerState("new-player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )

    plan = plan_session(
        GameMode.TUTORIAL,
        _configuration(),
        player_id="new-player",
        context={"ui": "discord"},
    )

    assert plan.session.mode is GameMode.STORY
    assert plan.missions == (FIRST_FLIGHT_MISSION_ID,)


def test_first_flight_is_story_on_cli_too(monkeypatch):
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
    assert plan.missions == (FIRST_FLIGHT_MISSION_ID,)


def test_completed_first_flight_advances_to_edge_of_space(monkeypatch):
    player = PlayerState("returning-player")
    player.missions_completed.append(FIRST_FLIGHT_MISSION_ID)
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
    assert plan.missions == (EDGE_OF_SPACE_MISSION_ID,)
    assert current_story_chapter("returning-player").mission_id == EDGE_OF_SPACE_MISSION_ID


def test_discord_first_flight_uses_limited_story_menu_without_tutorial_copy(monkeypatch):
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
    assert isinstance(configurator._service.service, SessionAwareFlightService)
    assert configurator._service.service.mode is GameMode.STORY

    content = configurator._step_content()
    assert "Your First Flight" in content
    assert "Tutorial" not in content
    assert "School let out twenty minutes ago" in content
    assert "same simulation" not in content

    context = configurator._game_entry_context
    assert context["mode"] is GameMode.STORY
    assert context["first_flight"] is True


def test_first_flight_menu_is_smaller_than_later_story_menu(monkeypatch):
    player = PlayerState("new-player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )
    first = game_menu._configurator_for_mode(
        service=object(),
        mode=GameMode.STORY,
        player_id="new-player",
        channel_kind="dm",
        on_finished=None,
    )
    first_gases = tuple(first._first_flight_options(0))
    assert first_gases == ("helium", "air")

    player.missions_completed.append(FIRST_FLIGHT_MISSION_ID)
    later = game_menu._configurator_for_mode(
        service=object(),
        mode=GameMode.STORY,
        player_id="new-player",
        channel_kind="dm",
        on_finished=None,
    )
    assert not isinstance(later, DiscoveryFirstFlightConfiguratorMixin)


def test_first_flight_handoff_uses_story_copy():
    view = game_menu.ContinueToStoryView(
        player_id="new-player",
        channel_kind="dm",
        service=object(),
    )

    assert "First Flight Complete" in view._resume_content
    assert "Tutorial" not in view._resume_content
    assert view.children[0].label == "Continue Story"
