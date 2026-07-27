from types import SimpleNamespace

from balloon_frontier.atmosphere_profile import AtmosphereProfileRepository
from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.launch_result import MissionResult
from balloon_frontier.progression import PlayerRegistry, PlayerState
from balloon_frontier.story import (
    ATMOSPHERIC_RIVER_MISSION_ID,
    COLLEGE_METEOROLOGY_CHAPTER,
    EDGE_OF_SPACE_MISSION_ID,
    STORY_DISCLAIMER,
    SUMMER_HOBBYIST_CHAPTER,
    add_story_results,
    current_story_chapter,
    story_intro,
    story_mission_for_player,
)
from balloon_frontier.weather_event import WeatherEvent


def test_edge_of_space_completion_advances_player_to_college(monkeypatch):
    player = PlayerState("student")
    player.missions_completed.append(EDGE_OF_SPACE_MISSION_ID)
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )

    assert current_story_chapter("student") is COLLEGE_METEOROLOGY_CHAPTER
    assert story_mission_for_player("student") == ATMOSPHERIC_RIVER_MISSION_ID


def test_early_story_establishes_university_of_washington_arc(monkeypatch):
    player = PlayerState("student")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )

    assert "University of Washington" in SUMMER_HOBBYIST_CHAPTER.introduction

    player.missions_completed.append(EDGE_OF_SPACE_MISSION_ID)
    chapter = current_story_chapter("student")
    briefing = story_intro("student")

    assert chapter is COLLEGE_METEOROLOGY_CHAPTER
    assert "University of Washington" in chapter.season
    assert "Dr. Elena Alvarez" in chapter.introduction
    assert "fictional" in chapter.introduction.lower()
    assert STORY_DISCLAIMER in briefing
    assert "not affiliated with or endorsed by" in briefing


def test_successful_sounding_records_profile(monkeypatch, tmp_path):
    from balloon_frontier import story

    repository = AtmosphereProfileRepository(tmp_path)
    monkeypatch.setattr(story, "atmosphere_profiles", repository)
    weather = WeatherEvent(1.2, -3.0, 0.3, -100.0, 0.1, "River", "Wet", "winds")
    telemetry = (
        SimpleNamespace(
            altitude_m=0.0,
            ambient_temperature_k=288.0,
            ambient_pressure_pa=101325.0,
            vx_mps=2.0,
            landed=False,
        ),
        SimpleNamespace(
            altitude_m=2500.0,
            ambient_temperature_k=272.0,
            ambient_pressure_pa=75000.0,
            vx_mps=-8.0,
            landed=False,
        ),
    )
    outcome = FlightOutcome(
        result=SimpleNamespace(telemetry=telemetry),
        weather=weather,
        mission_results=(
            MissionResult(ATMOSPHERIC_RIVER_MISSION_ID, True, 2500, "complete"),
        ),
    )

    updated = add_story_results(outcome, "student")

    assert repository.get("student") is not None
    assert updated.mission_results[-1].mission_id == "bonus_atmosphere_profile"
    assert updated.mission_results[-1].completed