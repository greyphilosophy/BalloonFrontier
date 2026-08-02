"""Guard player-facing narratives against impossible near-ground climb claims."""

from __future__ import annotations

from typing import Callable

_NO_LIFTOFF_ALTITUDE_M = 5.0
_NO_LIFTOFF_DURATION_S = 10.0
_SLOW_CLIMB_TEXT = (
    "📈 **Still climbing slowly...**\n"
    "  Your balloon is gaining altitude but not fast enough. "
    "Try heavier gas fill or lighter payloads."
)
_NO_LIFTOFF_TEXT = (
    "🛑 **Did not lift off**\n"
    "  The vehicle remained near the launch site and the flight ended before "
    "a sustained climb began."
)


def grounded_narrative_summary(original: Callable):
    """Wrap a narrative generator with a near-ground no-liftoff correction."""

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
            and time_of_flight < _NO_LIFTOFF_DURATION_S
        )
        if did_not_lift_off:
            return narrative.replace(_SLOW_CLIMB_TEXT, _NO_LIFTOFF_TEXT)
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
