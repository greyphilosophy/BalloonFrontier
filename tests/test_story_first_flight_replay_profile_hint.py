"""First-flight replay should not advertise controls the reduced view does not show."""

from balloon_frontier import story
from balloon_frontier.discord_ui import game_menu
from balloon_frontier.game_modes import GameMode
from balloon_frontier.progression import PlayerRegistry, PlayerState
from balloon_frontier.story import EDGE_OF_SPACE_MISSION_ID, FIRST_FLIGHT_MISSION_ID


def test_first_flight_replay_hides_recorded_atmosphere_hint(monkeypatch):
    player = PlayerState("player")
    player.missions_completed.extend((FIRST_FLIGHT_MISSION_ID, EDGE_OF_SPACE_MISSION_ID))
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )
    monkeypatch.setattr(story.atmosphere_profiles, "get", lambda player_id: object())

    configurator = game_menu._configurator_for_mode(
        service=object(),
        mode=GameMode.STORY,
        player_id="player",
        channel_kind="dm",
        on_finished=None,
        story_mission_id=FIRST_FLIGHT_MISSION_ID,
    )

    content = configurator._step_content()
    assert "Your First Flight" in content
    assert "recorded atmosphere profile is available below" not in content.lower()
