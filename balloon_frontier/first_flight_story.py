"""Narrative framing for the opening Story mission."""

from __future__ import annotations

from dataclasses import replace


FIRST_FLIGHT_MISSION_ID = "first_flight"
FIRST_FLIGHT_INTRODUCTION = (
    "School let out twenty minutes ago, but you're still standing at the edge of "
    "the athletic field with a balloon, a camera-equipped quadcopter, and a folding "
    "table covered in parts.\n\n"
    "The principal has agreed to let you photograph the campus from above. The "
    "school needs a new picture for its website, and hiring a photographer wasn't "
    "in the budget.\n\n"
    "Your quadcopter can carry the camera, but on its own the battery won't get it "
    "high enough for the shot you promised. The balloon beside you might solve "
    "that problem.\n\n"
    "Or it might drag your quadcopter into the trees.\n\n"
    "Either way, you've told everyone you're launching today."
)

FIRST_FLIGHT_PRIMARY_OBJECTIVE = (
    "Get an aerial photograph of the school and recover the camera safely."
)


def first_flight_briefing(chapter) -> str:
    """Render the opening chapter as fiction rather than configuration guidance."""

    text = (
        f"📖 **{chapter.title}**\n"
        f"*{chapter.season}*\n\n"
        f"{FIRST_FLIGHT_INTRODUCTION}\n\n"
        "**Primary objective**\n"
        f"{FIRST_FLIGHT_PRIMARY_OBJECTIVE}"
    )
    if chapter.bonus_challenges:
        bonuses = "\n".join(f"• {item}" for item in chapter.bonus_challenges)
        text += f"\n\n**Bonus challenges**\n{bonuses}"
    return text


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
            "dark. The launch failed, but the last image that made it back is "
            "surprisingly good. You save it before packing up. The design failed. "
            "The idea didn't."
        )
    return (
        "The flight ends without the clean photograph-and-recovery you promised. "
        "Before leaving the field, you make a list of what went wrong. The next "
        "version starts there."
    )


def add_first_flight_epilogue(outcome):
    """Append the opening chapter's result beat without changing rewards or physics."""

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
