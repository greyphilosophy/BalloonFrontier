"""Cursor-safe terminal playback for compact ANSI flight scenes."""

import os
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TextIO

from balloon_frontier.presentation import FlightMoment, FlightSceneBuilder, PlainTextSerializer, RenderFrame, TerminalAnsiSerializer

RESET = "\x1b[0m"
CLEAR = "\x1b[2J"
HOME = "\x1b[H"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"


@dataclass(frozen=True)
class TerminalCapabilities:
    animation: bool
    color: bool


def detect_capabilities(stream: TextIO = sys.stdout, *, no_animation: bool = False,
                        no_color: bool = False) -> TerminalCapabilities:
    is_tty = bool(getattr(stream, "isatty", lambda: False)())
    terminal_ok = os.environ.get("TERM", "") != "dumb"
    return TerminalCapabilities(
        animation=is_tty and terminal_ok and not no_animation,
        color=is_tty and terminal_ok and not no_color and "NO_COLOR" not in os.environ,
    )


class TerminalAnimationSession:
    def __init__(self, stream: TextIO = sys.stdout) -> None:
        self.stream = stream

    def __enter__(self):
        self.stream.write(HIDE_CURSOR + CLEAR + HOME)
        self.stream.flush()
        return self

    def draw(self, content: str) -> None:
        self.stream.write(HOME + content)
        self.stream.flush()

    def __exit__(self, exc_type, exc, traceback):
        self.stream.write(RESET + SHOW_CURSOR + "\n")
        self.stream.flush()
        return False


class TerminalFlightAnimator:
    def __init__(self, *, stream: TextIO = sys.stdout,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.stream = stream
        self.sleep = sleep
        self.builder = FlightSceneBuilder()

    def play(self, moments: Sequence[FlightMoment], *, speed: float = 1.0,
             no_animation: bool = False, no_color: bool = False) -> None:
        if not moments:
            return
        if speed <= 0:
            raise ValueError("Animation speed must be greater than zero")
        capabilities = detect_capabilities(self.stream, no_animation=no_animation, no_color=no_color)
        serializer = TerminalAnsiSerializer() if capabilities.color else PlainTextSerializer()
        if not capabilities.animation:
            self.stream.write(serializer.serialize(self.builder.build(RenderFrame(moments[-1]))) + "\n")
            self.stream.flush()
            return
        ticks_per_moment = 2
        delay = 0.12 / speed
        with TerminalAnimationSession(self.stream) as session:
            for index, moment in enumerate(moments):
                for tick in range(ticks_per_moment):
                    sway = (-1, 1)[(index + tick) % 2]
                    frame = RenderFrame(moment=moment, animation_tick=tick,
                                        balloon_offset_x=sway, cloud_offset_x=-sway,
                                        star_phase=index + tick)
                    session.draw(serializer.serialize(self.builder.build(frame)))
                    if not (index == len(moments) - 1 and tick == ticks_per_moment - 1):
                        self.sleep(delay)
