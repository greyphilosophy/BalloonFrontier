"""Guard player-facing narratives against impossible near-ground climb claims."""

from __future__ import annotations

from functools import wraps
from typing import Callable

_NO_LIFTOFF_ALTITUDE_M = 5.0
_SLOW_CLIMB_HEADING = "📈 **Still climbing slowly...**"
_NO_LIFTOFF_LINES = [
    "🛑 **Did not lift off**",
    "  The vehicle remained near the launch site and the flight ended before "
    "a sustained climb began.",
]


def _replace_slow_climb_block(narrative: str) -> str:
    """Replace only the slow-climb outcome block, preserving surrounding context."""
    lines = narrative.splitlines()
    try:
        index = lines.index(_SLOW_CLIMB_HEADING)
    except ValueError:
        return narrative

    end = index + 1
    while end < len(lines) and lines[end].startswith("  "):
        end += 1
    lines[index:end] = _NO_LIFTOFF_LINES
    return "\n".join(lines)


def grounded_narrative_summary(original: Callable):
    """Wrap a narrative generator with a near-ground no-liftoff correction."""

    @wraps(original)
    def generate(
        peak_altitude: float,
        burst: bool,
        landed: bool,
        crashed: bool,
        time_of_flight: float,
        mission_result=None,
        weather_briefing=None,
    ) -> str:
        narrative = original(
            peak_altitude=peak_altitude,
            burst=burst,
            landed=landed,
            crashed=crashed,
            time_of_flight=time_of_flight,
            mission_result=mission_result,
            weather_briefing=weather_briefing,
        )
        did_not_lift_off = (
            not burst
            and not landed
            and not crashed
            and peak_altitude < _NO_LIFTOFF_ALTITUDE_M
        )
        if did_not_lift_off:
            return _replace_slow_climb_block(narrative)
        return narrative

    return generate


def install_narrative_guard() -> None:
    """Install the correction once without changing other narrative branches."""
    from balloon_frontier import narrative_result

    current = narrative_result.generate_narrative_summary
    if getattr(current, "_balloon_frontier_grounded", False):
        return
    guarded = grounded_narrative_summary(current)
    guarded._balloon_frontier_grounded = True
    narrative_result.generate_narrative_summary = guarded
