"""Regression coverage for split first-flight results and Story continuation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from balloon_frontier.discord_ui import launch_handler
from balloon_frontier.discord_ui.game_menu import ContinueToStoryView
from balloon_frontier.tutorial_result_delivery import (
    _NEXT_ACTION_PROMPT,
    _TRAJECTORY_SENTINEL,
    _attach_next_action_prompt,
    _capture_trajectory,
    _captured_trajectory,
    _split_delivery_active,
    _split_discord_messages,
    _split_followup_failed,
    _split_send_results,
)


def test_first_flight_report_and_trajectory_are_sent_as_separate_messages():
    async def original_send(interaction, content):
        raise AssertionError("First-flight follow-ups should bypass truncating sender")

    interaction = SimpleNamespace(
        followup=SimpleNamespace(send=AsyncMock()),
    )
    wrapped_chart = _capture_trajectory(lambda: "```text\ntrajectory\n```")
    wrapped_send = _split_send_results(original_send)

    active_token = _split_delivery_active.set(True)
    chart_token = _captured_trajectory.set(None)
    fallback_token = _split_followup_failed.set(False)
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
        _split_followup_failed.reset(fallback_token)
        _captured_trajectory.reset(chart_token)
        _split_delivery_active.reset(active_token)

    assert interaction.followup.send.await_args_list[0].kwargs == {
        "content": "Launch report"
    }
    assert interaction.followup.send.await_args_list[1].kwargs == {
        "content": "```text\ntrajectory\n```"
    }


def test_split_followup_failure_delegates_to_safe_sender():
    original_send = AsyncMock(return_value=True)
    interaction = SimpleNamespace(
        followup=SimpleNamespace(
            send=AsyncMock(side_effect=RuntimeError("webhook expired")),
        ),
    )
    wrapped_send = _split_send_results(original_send)

    active_token = _split_delivery_active.set(True)
    fallback_token = _split_followup_failed.set(False)
    try:
        delivered = asyncio.run(
            wrapped_send(interaction, f"Launch report\n{_TRAJECTORY_SENTINEL}")
        )
    finally:
        _split_followup_failed.reset(fallback_token)
        _split_delivery_active.reset(active_token)

    assert delivered is True
    original_send.assert_awaited_once_with(interaction, "Launch report")


def test_next_action_prompt_is_story_only():
    interaction = SimpleNamespace(edit_original_response=AsyncMock())
    view = ContinueToStoryView(
        player_id="player",
        channel_kind="dm",
        service=object(),
    )

    active_token = _split_delivery_active.set(True)
    fallback_token = _split_followup_failed.set(False)
    try:
        attached = asyncio.run(_attach_next_action_prompt(interaction, view))
    finally:
        _split_followup_failed.reset(fallback_token)
        _split_delivery_active.reset(active_token)

    assert attached is True
    interaction.edit_original_response.assert_awaited_once_with(
        content=_NEXT_ACTION_PROMPT,
        view=view,
    )
    assert "Tutorial" not in _NEXT_ACTION_PROMPT
    assert "Replay" not in _NEXT_ACTION_PROMPT
    assert view.children[0].label == "Continue Story"


def test_fallback_report_is_not_overwritten_by_next_action_prompt():
    interaction = SimpleNamespace(edit_original_response=AsyncMock())
    view = object()

    active_token = _split_delivery_active.set(True)
    fallback_token = _split_followup_failed.set(True)
    try:
        attached = asyncio.run(_attach_next_action_prompt(interaction, view))
    finally:
        _split_followup_failed.reset(fallback_token)
        _split_delivery_active.reset(active_token)

    assert attached is True
    interaction.edit_original_response.assert_awaited_once_with(view=view)


def test_oversized_report_is_split_without_dropping_text():
    content = "\n".join(["A" * 900, "B" * 900, "C" * 900])
    messages = _split_discord_messages(content)

    assert len(messages) == 2
    assert all(len(message) <= 2000 for message in messages)
    assert "\n".join(messages) == content


def test_split_first_flight_report_is_not_truncated_before_message_split():
    configurator = SimpleNamespace(_balloon_frontier_split_result_delivery=True)
    content = "x" * 2500

    assert launch_handler._limit_result_content(configurator, content) == content


def test_non_split_report_keeps_legacy_discord_limit():
    content = "x" * 2500

    limited = launch_handler._limit_result_content(SimpleNamespace(), content)

    assert len(limited) == 2000
    assert limited.endswith("...")


def test_non_first_flight_chart_rendering_is_unchanged():
    wrapped = _capture_trajectory(lambda: "ordinary chart")
    assert wrapped() == "ordinary chart"
