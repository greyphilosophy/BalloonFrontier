import pytest

from balloon_frontier.game_modes import GameMode
from balloon_frontier.game_session import GameSession, SessionState


def configured_session(mode=GameMode.TUTORIAL):
    session = GameSession(mode=mode, player_id="player-1")
    session.set_configuration({"balloon": "36-inch", "gas": "helium"})
    return session


def test_constructs_for_every_game_mode():
    for mode in GameMode:
        session = GameSession(mode=mode)
        assert session.mode is mode
        assert session.state is SessionState.CONFIGURING
        assert session.session_id


def test_normalizes_mode_selection():
    assert GameSession(mode="free play").mode is GameMode.FREE_PLAY
    assert GameSession(mode=2).mode is GameMode.STORY


def test_rejects_invalid_session_id():
    for session_id in (" ", 123, None):
        with pytest.raises(ValueError, match="session_id"):
            GameSession(mode=GameMode.TUTORIAL, session_id=session_id)


def test_configuration_is_copied_frozen_and_required():
    values = {"balloon": "36-inch", "payloads": ["camera"]}
    session = GameSession(mode=GameMode.TUTORIAL)
    session.set_configuration(values)

    values["balloon"] = "150-inch"
    values["payloads"].append("radio")
    assert session.configuration == {
        "balloon": "36-inch",
        "payloads": ("camera",),
    }

    with pytest.raises(TypeError):
        session.configuration["balloon"] = "150-inch"
    with pytest.raises(AttributeError):
        session.configuration["payloads"].append("radio")

    empty = GameSession(mode=GameMode.TUTORIAL)
    with pytest.raises(ValueError, match="must not be empty"):
        empty.set_configuration({})


def test_configuration_remains_locked_after_ready():
    session = configured_session()
    session.mark_ready()

    with pytest.raises(TypeError):
        session.configuration["gas"] = "hydrogen"
    with pytest.raises(ValueError, match="requires state configuring"):
        session.set_configuration({"gas": "hydrogen"})


def test_lifecycle_fields_are_read_only():
    session = configured_session()

    with pytest.raises(AttributeError):
        session.state = SessionState.COMPLETED
    with pytest.raises(AttributeError):
        session.launch_result = {"peak_altitude_m": 99999}

    assert session.state is SessionState.CONFIGURING
    assert session.launch_result is None


def test_complete_lifecycle_retains_result():
    session = configured_session()
    session.mark_ready()
    session.launch()
    result = {"peak_altitude_m": 12000}
    session.complete(result)

    assert session.state is SessionState.COMPLETED
    assert session.launch_result is result
    assert session.is_terminal


def test_mark_ready_requires_configuration():
    session = GameSession(mode=GameMode.SCENARIO)
    with pytest.raises(ValueError, match="requires configuration"):
        session.mark_ready()


def test_invalid_transitions_are_rejected():
    session = configured_session()
    with pytest.raises(ValueError, match="requires state ready"):
        session.launch()

    session.mark_ready()
    with pytest.raises(ValueError, match="requires state configuring"):
        session.set_configuration({"gas": "hydrogen"})

    session.launch()
    with pytest.raises(ValueError, match="requires state ready"):
        session.launch()


def test_cancel_is_terminal():
    session = GameSession(mode=GameMode.FREE_PLAY)
    session.cancel()

    assert session.state is SessionState.CANCELLED
    assert session.is_terminal
    with pytest.raises(ValueError, match="cannot cancel"):
        session.cancel()
