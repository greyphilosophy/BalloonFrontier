"""Regression coverage for split tutorial results and next-step controls."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from balloon_frontier.game_modes import GameMode
from balloon_frontier.tutorial_result_delivery import (
    TutorialNextActionView,
    _TRAJECTORY_SENTINEL,
    _capture_trajectory,
    _captured_trajectory,
    _split_delivery_active,
    _split_send_results,
)


def test_tutorial_report_and_trajectory_are_sent_as_separate_messages():
    async def original_send(interaction, content):
        interaction.sent.append(content)
        return True

    interaction = SimpleNamespace(
        sent=[],
        followup=SimpleNamespace(send=AsyncMock()),
    )
    wrapped_chart = _capture_trajectory(lambda: "```text\ntrajectory\n```")
    wrapped_send = _split_send_results(original_send)

    active_token = _split_delivery_active.set(True)
    chart_token = _captured_trajectory.set(None)
    try:
        sentinel = wrapped_chart()
        assert sentinel == _TRAJECTORY_SENTINEL

        asyncio.run(
            wrapped_send(
                interaction,
                f"Launch report\n{_TRAJECTORY_SENTINEL}",
            )
        )
    finally:
        _captured_trajectory.reset(chart_token)
        _split_delivery_active.reset(active_token)

    assert interaction.sent == ["Launch report"]
    interaction.followup.send.assert_awaited_once_with(
        content="```text\ntrajectory\n```"
    )


def test_non_tutorial_chart_rendering_is_unchanged():
    wrapped = _capture_trajectory(lambda: "ordinary chart")
    assert wrapped() == "ordinary chart"


def test_completion_view_offers_replay_and_continue_story():
    view = TutorialNextActionView(
        player_id="42",
        channel_kind="dm",
        service=SimpleNamespace(),
    )

    assert [item.label for item in view.children] == [
        "Replay Tutorial",
        "Continue Story",
    ]
    assert [item.mode for item in view.children] == [
        GameMode.TUTORIAL,
        GameMode.STORY,
    ]

    owner = SimpleNamespace(user=SimpleNamespace(id=42))
    stranger = SimpleNamespace(user=SimpleNamespace(id=99))
    assert asyncio.run(view.interaction_check(owner))
    assert not asyncio.run(view.interaction_check(stranger))


def test_completion_prompt_asks_the_player_what_to_do_next():
    view = TutorialNextActionView(
        player_id="42",
        channel_kind="dm",
        service=SimpleNamespace(),
    )

    assert "replay the tutorial" in view._resume_content.lower()
    assert "continue the story" in view._resume_content.lower()
