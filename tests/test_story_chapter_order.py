"""Regression tests for a single canonical Story chapter ordering."""

from balloon_frontier import story
from balloon_frontier import story_mission_select
from balloon_frontier.progression import PlayerRegistry, PlayerState


def _player(monkeypatch, completed=()):
    player = PlayerState("player")
    player.missions_completed.extend(completed)
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )
    return player


def test_story_declares_the_canonical_chapter_order():
    assert [chapter.mission_id for chapter in story.STORY_CHAPTERS] == [
        story.FIRST_FLIGHT_MISSION_ID,
        story.EDGE_OF_SPACE_MISSION_ID,
        story.ATMOSPHERIC_RIVER_MISSION_ID,
    ]


def test_progression_and_mission_select_follow_the_same_runtime_order(monkeypatch):
    _player(monkeypatch)
    reordered = (
        story.COLLEGE_METEOROLOGY_CHAPTER,
        story.FIRST_FLIGHT_CHAPTER,
        story.SUMMER_HOBBYIST_CHAPTER,
    )
    monkeypatch.setattr(story, "STORY_CHAPTERS", reordered)

    assert story.current_story_chapter("player") is reordered[0]
    choices = story_mission_select.story_mission_choices("player")
    assert [choice.chapter for choice in choices] == [reordered[0]]
    assert choices[0].is_next


def test_current_story_chapter_returns_last_canonical_chapter_when_all_are_complete(
    monkeypatch,
):
    completed = (
        story.FIRST_FLIGHT_MISSION_ID,
        story.EDGE_OF_SPACE_MISSION_ID,
        story.ATMOSPHERIC_RIVER_MISSION_ID,
    )
    _player(monkeypatch, completed=completed)

    assert story.current_story_chapter("player") is story.STORY_CHAPTERS[-1]
