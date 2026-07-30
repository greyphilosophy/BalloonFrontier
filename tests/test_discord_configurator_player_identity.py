from balloon_frontier.discord_ui import game_menu
from balloon_frontier.game_modes import GameMode
from balloon_frontier.progression import PlayerRegistry, PlayerState


def test_configurator_reads_progression_for_bound_session_player(monkeypatch):
    player = PlayerState("player")
    player.reputation = 17
    player.budget = 2500
    lookups = []

    def get_player(cls, player_id):
        lookups.append(player_id)
        return player

    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(get_player),
    )

    configurator = game_menu._configurator_for_mode(
        service=object(),
        mode=GameMode.FREE_PLAY,
        player_id="player",
        channel_kind="guild",
        on_finished=None,
    )

    assert configurator._get_player_state() is player
    assert lookups == ["player"]

    content = configurator._step_content()
    assert "17 reputation" in content
    assert "$2500 budget" in content
    assert lookups == ["player", "player"]
