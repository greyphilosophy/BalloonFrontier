"""Story starts with the first-flight tutorial without presenting it as a tutorial."""

from balloon_frontier.career_prologue import DiscoveryFirstFlightConfiguratorMixin
from balloon_frontier.discord_ui import game_menu
from balloon_frontier.game_modes import GameMode
from balloon_frontier.progression import PlayerRegistry, PlayerState
from balloon_frontier.session_controller import plan_session


def _configuration():
    return {
        "gas": "helium",
        "envelope": "mylar",
        "fill_mode": "auto",
        "payloads": ("quadcopter",),
        "site": "field",
    }


def test_new_story_player_gets_first_flight_session(monkeypatch):
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
    content = configurator._step_content()
    assert "Your First Flight" in content
    assert "Tutorial" not in content
    assert "Green buttons" not in content
    assert all(item.style.name != "success" for item in configurator.children)
