"""Story-mode chapters, progression, and telemetry-backed challenges."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import atan2, degrees, hypot
from statistics import pstdev

import discord

from balloon_frontier.atmosphere import StandardAtmosphereProvider
from balloon_frontier.atmosphere_profile import AtmosphereProfile, atmosphere_profiles
from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.launch_result import MissionResult
from balloon_frontier.progression import PlayerRegistry
from balloon_frontier.sounding_profile import record_sounding_profile

FIRST_FLIGHT_MISSION_ID = "first_flight"
EDGE_OF_SPACE_MISSION_ID = "edge_of_space"
ATMOSPHERIC_RIVER_MISSION_ID = "atmospheric_river_sounding"

STORY_DISCLAIMER = (
    "Educational fiction: Balloon Frontier is not affiliated with or endorsed by "
    "the University of Washington. Dr. Elena Alvarez, the research project, "
    "dialogue, and events are fictional; real institutions are referenced for "
    "educational context."
)


@dataclass(frozen=True, slots=True)
class StoryChapter:
    id: str
    title: str
    season: str
    introduction: str
    mission_id: str
    primary_objective: str
    bonus_challenges: tuple[str, ...] = ()
    future_challenges: tuple[str, ...] = ()


FIRST_FLIGHT_CHAPTER = StoryChapter(
    id="first_flight",
    title="Your First Flight",
    season="The beginning",
    introduction=(
        "You have a balloon, a camera, and an open field. Start with a small set "
        "of choices, make a real launch, and learn from what the same simulation "
        "used everywhere else says happened. There is no hidden training physics "
        "and no prescribed winning configuration."
    ),
    mission_id=FIRST_FLIGHT_MISSION_ID,
    primary_objective=(
        "Launch a camera payload from the field and recover it without crashing."
    ),
    bonus_challenges=("Compare a different gas or fill on a later flight",),
)

SUMMER_HOBBYIST_CHAPTER = StoryChapter(
    id="summer_hobbyist",
    title="Summer Project: Edge of Space",
    season="Summer after senior year",
    introduction=(
        "Your first flight worked well enough to make the project feel real. Your "
        "last balloon video is starting to get views and earn a little revenue. "
        "With your first term at the University of Washington beginning in the fall, "
        "this is your chance to finish the summer with a serious engineering project. "
        "Now everyone is waiting for the maiden flight of your newest design. "
        "Show them something spectacular—without spending money you do not have."
    ),
    mission_id=EDGE_OF_SPACE_MISSION_ID,
    primary_objective=(
        "Send a camera to at least 30 km and return usable footage of Earth's curvature."
    ),
    bonus_challenges=("Stable footage", "Controlled recovery"),
    future_challenges=(
        "Capture Earth and the Moon in the same video.",
        "Record the longest sunset.",
    ),
)

COLLEGE_METEOROLOGY_CHAPTER = StoryChapter(
    id="college_meteorology",
    title="Atmospheric River",
    season="Freshman fall — University of Washington",
    introduction=(
        "Your first quarter at the University of Washington has barely begun when "
        "Dr. Elena Alvarez, a fictional professor of atmospheric science, asks about "
        "the balloon project you launched over the summer. She is organizing a "
        "fictional field campaign to study an atmospheric river approaching western "
        "Washington. 'We're launching several soundings over the next few days. "
        "Want to turn that engineering project into scientific atmospheric data?'"
    ),
    mission_id=ATMOSPHERIC_RIVER_MISSION_ID,
    primary_objective=(
        "Carry weather instruments through the troposphere and recover a vertical "
        "profile of wind, temperature, and pressure."
    ),
    bonus_challenges=("Reach 18 km", "Recover the instruments"),
)


# Canonical Story progression order. Add or reorder chapters here; progression,
# Mission Select, replay lookup, and default Story mission resolution all consume
# this same sequence.
STORY_CHAPTERS: tuple[StoryChapter, ...] = (
    FIRST_FLIGHT_CHAPTER,
    SUMMER_HOBBYIST_CHAPTER,
    COLLEGE_METEOROLOGY_CHAPTER,
)


def next_incomplete_story_chapter(completed_mission_ids) -> StoryChapter | None:
    """Return the earliest canonical chapter whose mission is not completed."""

    completed = set(completed_mission_ids or ())
    return next(
        (
            chapter
            for chapter in STORY_CHAPTERS
            if chapter.mission_id not in completed
        ),
        None,
    )


def story_chapter_for_mission(mission_id: str) -> StoryChapter:
    """Look up a Story chapter by mission ID using the canonical chapter list."""

    for chapter in STORY_CHAPTERS:
        if chapter.mission_id == mission_id:
            return chapter
    raise ValueError(f"Unknown Story mission: {mission_id!r}")


def current_story_chapter(player_id: str | None = None) -> StoryChapter:
    if not player_id:
        return STORY_CHAPTERS[0]
    player = PlayerRegistry.get_or_create(str(player_id))
    return next_incomplete_story_chapter(player.missions_completed) or STORY_CHAPTERS[-1]


def _wind_label(x_mps: float, y_mps: float) -> str:
    speed = hypot(x_mps, y_mps)
    if speed < 0.05:
        return "calm"
    bearing = (degrees(atan2(x_mps, y_mps)) + 360.0) % 360.0
    directions = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    direction = directions[int((bearing + 22.5) // 45.0) % 8]
    return f"{speed:.1f} {direction}"


def _select_profile_layers(layers: tuple, max_layers: int) -> tuple:
    limit = max(1, int(max_layers))
    if len(layers) <= limit:
        return layers
    if limit == 1:
        return (layers[-1],)
    indexes = [
        round(position * (len(layers) - 1) / (limit - 1))
        for position in range(limit)
    ]
    return tuple(layers[index] for index in indexes)


def format_atmosphere_profile(
    profile: AtmosphereProfile,
    *,
    max_layers: int = 8,
) -> str:
    """Format a compact Discord-safe sounding table spanning the full profile."""

    layers = profile.layers
    if not layers:
        return "📡 **Recorded atmosphere**\nNo measured layers are available."
    selected = _select_profile_layers(layers, max_layers)
    lines = [
        "📡 **Recorded atmosphere**",
        "` Alt km | Temp °C | Press kPa | Wind m/s `",
    ]
    for layer in selected:
        lines.append(
            f"` {layer.altitude_m / 1000:6.1f} |"
            f" {layer.temperature_k - 273.15:7.1f} |"
            f" {layer.pressure_pa / 1000:9.1f} |"
            f" {_wind_label(layer.wind_x_mps, layer.wind_y_mps):>8} `"
        )
    if len(layers) > len(selected):
        lines.append(f"*{len(layers) - len(selected)} intermediate layers omitted.*")
    if not profile.wind_measurements_available:
        lines.append("*Legacy profile: launch-site wind will be generated during replay.*")
    return "\n".join(lines)


def story_chapter_intro(
    chapter: StoryChapter,
    *,
    player_id: str | None = None,
    atmosphere_locked: bool = False,
    include_disclaimer: bool = True,
) -> str:
    """Render Story briefing text for an explicit chapter."""

    bonuses = "\n".join(f"• {item}" for item in chapter.bonus_challenges)
    text = (
        f"📖 **{chapter.title}**\n"
        f"*{chapter.season}*\n\n"
        f"{chapter.introduction}\n\n"
        "**Primary objective**\n"
        f"{chapter.primary_objective}"
    )
    if bonuses:
        text += f"\n\n**Bonus challenges**\n{bonuses}"
    if chapter.future_challenges:
        future = "\n".join(f"• {item}" for item in chapter.future_challenges)
        text += f"\n\n**Future cinematic challenges**\n{future}"
    if atmosphere_locked:
        text += (
            "\n\n🔒 **Measured conditions selected.** "
            "This recorded atmosphere will drive the next launch."
        )
    elif player_id and atmosphere_profiles.get(str(player_id)) is not None:
        text += "\n\n📡 A recorded atmosphere profile is available below."
    if include_disclaimer and chapter is not FIRST_FLIGHT_CHAPTER:
        text += f"\n\n*{STORY_DISCLAIMER}*"
    return text


def story_intro(
    player_id: str | None = None,
    *,
    atmosphere_locked: bool = False,
    include_disclaimer: bool = True,
) -> str:
    return story_chapter_intro(
        current_story_chapter(player_id),
        player_id=player_id,
        atmosphere_locked=atmosphere_locked,
        include_disclaimer=include_disclaimer,
    )


def story_mission_for_player(player_id: str | None = None) -> str:
    return current_story_chapter(player_id).mission_id


def _stable_footage(outcome: FlightOutcome) -> bool:
    velocities = [
        point.velocity_mps
        for point in outcome.result.telemetry
        if not point.landed
    ]
    return len(velocities) >= 2 and pstdev(velocities) <= 8.0


def _controlled_recovery(outcome: FlightOutcome) -> bool:
    telemetry = tuple(outcome.result.telemetry)
    return any(point.landed for point in telemetry) and not any(
        point.crashed for point in telemetry
    )


def _launch_site_id(outcome: FlightOutcome) -> str:
    launch_request = getattr(outcome.result, "launch_request", None)
    return str(getattr(launch_request, "launch_site_id", "field"))


def add_story_results(
    outcome: FlightOutcome,
    player_id: str | None = None,
) -> FlightOutcome:
    existing = tuple(outcome.mission_results)
    mission_ids = {item.mission_id for item in existing}
    if EDGE_OF_SPACE_MISSION_ID in mission_ids:
        stable = _stable_footage(outcome)
        recovered = _controlled_recovery(outcome)
        bonuses = (
            MissionResult(
                "bonus_stable_footage",
                stable,
                0,
                "The camera returned steady, watchable footage."
                if stable
                else "The footage was too unstable to earn the stable-flight bonus.",
            ),
            MissionResult(
                "bonus_controlled_recovery",
                recovered,
                0,
                "The payload completed a controlled recovery."
                if recovered
                else "The payload was not recovered under control.",
            ),
        )
        return replace(outcome, mission_results=existing + bonuses)

    sounding = next(
        (
            item
            for item in existing
            if item.mission_id == ATMOSPHERIC_RIVER_MISSION_ID
        ),
        None,
    )
    if sounding and sounding.completed and player_id and outcome.weather is not None:
        provider = outcome.atmosphere_provider or StandardAtmosphereProvider(
            site_id=_launch_site_id(outcome),
            wind_enabled=True,
        )
        profile = record_sounding_profile(
            outcome.result.telemetry,
            outcome.weather,
            provider,
        )
        atmosphere_profiles.save(str(player_id), profile)
        recorded = MissionResult(
            "bonus_atmosphere_profile",
            bool(profile.layers),
            0,
            f"Recorded {len(profile.layers)} atmospheric layers for future launches.",
        )
        return replace(outcome, mission_results=existing + (recorded,))
    return outcome


def add_story_bonus_results(outcome: FlightOutcome) -> FlightOutcome:
    return add_story_results(outcome)


class _LockAtmosphereButton(discord.ui.Button):
    def __init__(self, parent: "StoryConfiguratorMixin") -> None:
        super().__init__(
            label="Use Recorded Atmosphere",
            style=discord.ButtonStyle.success,
            custom_id="story_lock_recorded_atmosphere",
        )
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        player_id = getattr(self.parent_view._service, "story_player_id", None)
        locked = bool(player_id) and atmosphere_profiles.lock_for_next_flight(
            str(player_id)
        )
        self.parent_view._atmosphere_locked = locked
        self.parent_view.build_buttons()
        await self.parent_view._send_step(interaction)


class StoryConfiguratorMixin:
    """Add the active Story briefing and recorded-atmosphere controls."""

    def __init__(self, *args, **kwargs):
        self._atmosphere_locked = False
        super().__init__(*args, **kwargs)

    def _step_content(self) -> str:
        player_id = getattr(self._service, "story_player_id", None)
        text = story_intro(
            player_id,
            atmosphere_locked=self._atmosphere_locked,
            include_disclaimer=self._current_step == 0,
        )
        if player_id:
            profile = atmosphere_profiles.get(str(player_id))
            if profile is not None:
                text += "\n\n" + format_atmosphere_profile(profile)
        return text + "\n\n" + super()._step_content()

    def build_buttons(self):
        super().build_buttons()
        player_id = getattr(self._service, "story_player_id", None)
        has_profile = bool(player_id) and atmosphere_profiles.get(
            str(player_id)
        ) is not None
        if self._current_step == 5 and has_profile and not self._atmosphere_locked:
            self.add_item(_LockAtmosphereButton(self))
