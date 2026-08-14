"""Regression coverage for First Flight narrative framing and Discord delivery."""

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

from balloon_frontier.discord_ui import game_menu
from balloon_frontier.first_flight_story import add_first_flight_epilogue
from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import MissionResult
from balloon_frontier.progression import PlayerRegistry, PlayerState
from balloon_frontier.story import FIRST_FLIGHT_MISSION_ID


class FakeResponse:
    def __init__(self):
        self.edited = None

    async def edit_message(self, *, content, view):
        self.edited = (content, view)


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *, content, view, wait=False):
        message = SimpleNamespace(content=content, view=view)
        self.sent.append((content, view, wait, message))
        return message


class FakeInteraction:
    def __init__(self, user_id="player"):
        self.user = SimpleNamespace(id=user_id)
        self.message = object()
        self.response = FakeResponse()
        self.followup = FakeFollowup()


def _player(monkeypatch):
    player = PlayerState("player")
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )
    return player


def test_first_flight_story_and_configuration_are_separate_messages(monkeypatch):
    _player(monkeypatch)
    interaction = FakeInteraction()

    asyncio.run(
        game_menu.start_mode(
            interaction,
            service=object(),
            mode=GameMode.STORY,
            player_id="player",
            channel_kind="dm",
            story_mission_id=FIRST_FLIGHT_MISSION_ID,
        )
    )

    story_content, story_view = interaction.response.edited
    assert story_view is None
    assert "School let out twenty minutes ago" in story_content
    assert "principal" in story_content
    assert "Get an aerial photograph of the school" in story_content
    assert "Balloon Configuration" not in story_content

    assert len(interaction.followup.sent) == 1
    config_content, config_view, wait, config_message = interaction.followup.sent[0]
    assert wait is True
    assert "Balloon Configuration" in config_content
    assert "School let out twenty minutes ago" not in config_content
    assert "Your First Flight" not in config_content
    assert config_view._msg is config_message

    # Once the briefing is external, later wizard renders remain configuration-only.
    assert "Your First Flight" not in config_view._step_content()


def test_first_flight_success_epilogue_hooks_the_next_story_question():
    result = MissionResult(
        mission_id=FIRST_FLIGHT_MISSION_ID,
        completed=True,
        reward=500,
        explanation="Mission completed.",
    )
    outcome = FlightOutcome(
        result=SimpleNamespace(crashed=False),
        mission_results=(result,),
    )

    updated = add_first_flight_epilogue(outcome)

    assert updated.mission_results[0].completed is True
    assert updated.mission_results[0].reward == 500
    assert '"How high could this thing go?"' in updated.mission_results[0].explanation


def test_first_flight_crash_epilogue_reacts_to_the_simulation():
    result = MissionResult(
        mission_id=FIRST_FLIGHT_MISSION_ID,
        completed=False,
        reward=0,
        explanation="Mission not completed.",
    )
    outcome = FlightOutcome(
        result=SimpleNamespace(crashed=True),
        mission_results=(result,),
    )

    updated = add_first_flight_epilogue(outcome)

    explanation = updated.mission_results[0].explanation
    assert "after dark" in explanation
    assert "last image" in explanation
    assert "The idea didn't" in explanation
