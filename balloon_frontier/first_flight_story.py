"""Narrative result framing for the opening Story mission."""

from __future__ import annotations

from dataclasses import replace


def first_flight_briefing(chapter) -> str:
    """Render the canonical opening Story chapter for Discord."""

    from balloon_frontier.story import story_chapter_intro

    return story_chapter_intro(chapter, include_disclaimer=False)


def first_flight_epilogue(*, completed: bool, crashed: bool) -> str:
    """Return a simulation-grounded story beat for the first-flight result."""

    if completed:
        return (
            "Back on the ground, the principal keeps zooming in on the photograph. "
            '"This is exactly what we needed." Then they look from the image to your '
            'balloon rig. "How high could this thing go?"'
        )
    if crashed:
        return (
            "You're still collecting broken pieces from the athletic field after "
            "dark. Whatever the camera managed to capture, the aircraft isn't coming "
            "home intact. You save the flight log before packing up. The design "
            "failed. The idea didn't."
        )
    return (
        "The flight ends without the clean photograph-and-recovery you promised. "
        "Before leaving the field, you make a list of what went wrong. The next "
        "version starts there."
    )


def add_first_flight_epilogue(outcome):
    """Append the opening chapter's result beat without changing rewards or physics."""

    from balloon_frontier.story import FIRST_FLIGHT_MISSION_ID

    mission_results = tuple(getattr(outcome, "mission_results", ()) or ())
    if not mission_results:
        return outcome

    crashed = bool(getattr(outcome.result, "crashed", False))
    changed = False
    updated_results = []
    for result in mission_results:
        if result.mission_id != FIRST_FLIGHT_MISSION_ID:
            updated_results.append(result)
            continue
        changed = True
        epilogue = first_flight_epilogue(
            completed=bool(result.completed),
            crashed=crashed,
        )
        updated_results.append(
            replace(result, explanation=f"{result.explanation} {epilogue}")
        )

    if not changed:
        return outcome
    return replace(outcome, mission_results=tuple(updated_results))
