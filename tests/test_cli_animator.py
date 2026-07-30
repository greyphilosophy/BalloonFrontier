import io

from balloon_frontier.cli_ui.animator import HIDE_CURSOR, SHOW_CURSOR, TerminalAnimationSession, TerminalFlightAnimator, detect_capabilities
from balloon_frontier.presentation import build_flight_moments


class FakeTTY(io.StringIO):
    def isatty(self): return True


class FakePipe(io.StringIO):
    def isatty(self): return False


def moments():
    return build_flight_moments([
        {"time": 0, "alt": 0, "vel": 0}, {"time": 5, "alt": 20, "vel": 4},
        {"time": 800, "alt": 13000, "vel": 7}, {"time": 1600, "alt": 30000, "vel": 1},
        {"time": 2400, "alt": 0, "vel": 0, "landed": True},
    ])


def test_non_tty_prints_static_plain_frame_without_cursor_codes():
    stream = FakePipe()
    TerminalFlightAnimator(stream=stream, sleep=lambda _: None).play(moments())
    output = stream.getvalue()
    assert HIDE_CURSOR not in output and SHOW_CURSOR not in output and "\x1b" not in output
    assert "BALLOON FRONTIER" in output


def test_tty_animation_restores_cursor_and_uses_requested_ticks():
    stream = FakeTTY(); delays = []
    TerminalFlightAnimator(stream=stream, sleep=delays.append).play(moments())
    assert HIDE_CURSOR in stream.getvalue() and SHOW_CURSOR in stream.getvalue()
    assert len(delays) == len(moments()) * 2 - 1


def test_session_restores_cursor_after_exception():
    stream = FakeTTY()
    try:
        with TerminalAnimationSession(stream): raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert SHOW_CURSOR in stream.getvalue()


def test_flags_environment_and_invalid_speed(monkeypatch):
    stream = FakeTTY(); monkeypatch.setenv("NO_COLOR", "1")
    caps = detect_capabilities(stream)
    assert caps.animation and not caps.color
    assert not detect_capabilities(stream, no_animation=True).animation
    try: TerminalFlightAnimator(stream=stream).play(moments(), speed=0)
    except ValueError: pass
    else: raise AssertionError("expected ValueError")
