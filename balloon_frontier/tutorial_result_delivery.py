"""Split first-flight Story results and attach the next Story action.

The module name is retained temporarily for import compatibility. There is no
separate tutorial mode or tutorial-only simulation path.
"""

from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
import logging

logger = logging.getLogger(__name__)

_TRAJECTORY_SENTINEL = "[[BALLOON_FRONTIER_TRAJECTORY_MESSAGE]]"
_NEXT_ACTION_PROMPT = (
    "🎈 **First Flight Complete**\n\n"
    "Your progress is saved. Continue the story when you are ready."
)
_split_delivery_active: ContextVar[bool] = ContextVar(
    "balloon_frontier_split_delivery_active",
    default=False,
)
_captured_trajectory: ContextVar[str | None] = ContextVar(
    "balloon_frontier_captured_trajectory",
    default=None,
)
_split_followup_failed: ContextVar[bool] = ContextVar(
    "balloon_frontier_split_followup_failed",
    default=False,
)


def _first_flight_launch_scope(original):
    @wraps(original)
    async def run(configurator, interaction, service):
        context = getattr(configurator, "_game_entry_context", None) or {}
        if not context.get("first_flight"):
            return await original(configurator, interaction, service)

        marker_name = "_balloon_frontier_split_result_delivery"
        missing = object()
        previous_marker = getattr(configurator, marker_name, missing)
        setattr(configurator, marker_name, True)

        active_token = _split_delivery_active.set(True)
        chart_token = _captured_trajectory.set(None)
        fallback_token = _split_followup_failed.set(False)
        try:
            return await original(configurator, interaction, service)
        finally:
            _split_followup_failed.reset(fallback_token)
            _captured_trajectory.reset(chart_token)
            _split_delivery_active.reset(active_token)
            if previous_marker is missing:
                try:
                    delattr(configurator, marker_name)
                except AttributeError:
                    pass
            else:
                setattr(configurator, marker_name, previous_marker)

    run._balloon_frontier_split_tutorial_delivery = True
    return run


# Backward-compatible private name used by older focused tests.
_tutorial_launch_scope = _first_flight_launch_scope


def _capture_trajectory(original):
    @wraps(original)
    def render(*args, **kwargs):
        chart = original(*args, **kwargs)
        if not _split_delivery_active.get() or not chart:
            return chart
        _captured_trajectory.set(str(chart))
        return _TRAJECTORY_SENTINEL

    render._balloon_frontier_capture_tutorial_trajectory = True
    return render


def _without_trajectory_sentinel(content: str) -> str:
    return str(content).replace("\n" + _TRAJECTORY_SENTINEL, "").replace(
        _TRAJECTORY_SENTINEL,
        "",
    ).rstrip()


def _split_discord_messages(content: str, limit: int = 2000) -> tuple[str, ...]:
    """Split plain report text at line boundaries without dropping content."""
    text = str(content).strip()
    if not text:
        return ()
    if len(text) <= limit:
        return (text,)

    messages: list[str] = []
    current = ""
    for line in text.splitlines():
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            messages.append(current)
            current = ""
        while len(line) > limit:
            messages.append(line[:limit])
            line = line[limit:]
        current = line
    if current:
        messages.append(current)
    return tuple(messages)


async def _send_chart_followup(interaction, chart: str | None) -> bool:
    if not chart:
        return False
    followup = getattr(interaction, "followup", None)
    if followup is None or not hasattr(followup, "send"):
        return False
    await followup.send(content=chart)
    return True


def _split_send_results(original):
    @wraps(original)
    async def send(interaction, content: str):
        if not _split_delivery_active.get():
            return await original(interaction, content)

        report = _without_trajectory_sentinel(content)
        followup = getattr(interaction, "followup", None)
        if followup is None or not hasattr(followup, "send"):
            return await original(interaction, report)

        try:
            for message in _split_discord_messages(report):
                await followup.send(content=message)
            await _send_chart_followup(interaction, _captured_trajectory.get())
            return True
        except Exception:
            logger.warning(
                "Split first-flight follow-up delivery failed; using safe fallback",
                exc_info=True,
            )
            _split_followup_failed.set(True)
            return await original(interaction, report)

    send._balloon_frontier_split_tutorial_messages = True
    return send


def _split_edit_results(original):
    @wraps(original)
    async def edit(interaction, content: str, continue_view):
        if not _split_delivery_active.get():
            return await original(interaction, content, continue_view)

        report = _without_trajectory_sentinel(content)
        chart = _captured_trajectory.get()
        followup = getattr(interaction, "followup", None)
        if followup is not None and hasattr(followup, "send"):
            messages = _split_discord_messages(report)
            first = messages[0] if messages else "Flight complete."
            await original(interaction, first, continue_view)
            for message in messages[1:]:
                await followup.send(content=message)
            await _send_chart_followup(interaction, chart)
            return None

        combined = report
        if chart and len(report) + len(chart) + 2 <= 2000:
            combined = f"{report}\n\n{chart}"
        return await original(interaction, combined, continue_view)

    edit._balloon_frontier_split_tutorial_messages = True
    return edit


def _build_next_action_view(configurator, interaction, result):
    context = getattr(configurator, "_game_entry_context", None) or {}
    if not context.get("first_flight"):
        return None
    completed = any(
        mission.mission_id == "first_flight" and mission.completed
        for mission in result.mission_results
    )
    if not completed:
        return None

    try:
        from balloon_frontier.discord_ui.game_menu import ContinueToStoryView

        view = ContinueToStoryView(
            player_id=str(interaction.user.id),
            channel_kind=context["channel_kind"],
            service=context["service"],
            on_finished=context.get("on_finished"),
            on_view_changed=context.get("on_view_changed"),
        )
    except Exception:
        logger.exception("Failed to build first-flight continuation controls")
        return None

    setattr(configurator, "_tutorial_continuation_handled", True)
    callback = context.get("on_view_changed")
    if callback is not None:
        try:
            callback(view)
        except Exception:
            logger.exception("Failed to register first-flight continuation view")
    return view


async def _attach_next_action_prompt(interaction, continue_view) -> bool:
    """Deliver Story continuation without rewriting a successful flight GIF."""
    if continue_view is None:
        return False

    followup = getattr(interaction, "followup", None)
    can_follow_up = followup is not None and hasattr(followup, "send")
    followup_failed = _split_followup_failed.get()

    try:
        if can_follow_up and not followup_failed:
            await followup.send(
                content=_NEXT_ACTION_PROMPT,
                view=continue_view,
            )
            return True

        # If follow-up delivery has already failed, preserve the fallback report's
        # content and attach only the controls to the original response. For
        # transports without follow-up support, editing is the last-resort path.
        kwargs = {"view": continue_view}
        if not followup_failed:
            kwargs["content"] = _NEXT_ACTION_PROMPT
        await interaction.edit_original_response(**kwargs)
    except Exception:
        logger.warning(
            "First flight completed, but continuation controls could not be delivered",
            exc_info=True,
        )
        return False
    return True


def install_tutorial_result_delivery() -> None:
    """Install first-flight split delivery while preserving the old installer name."""
    from balloon_frontier.discord_ui import launch_handler

    if not getattr(
        launch_handler.run_launch,
        "_balloon_frontier_split_tutorial_delivery",
        False,
    ):
        launch_handler.run_launch = _first_flight_launch_scope(launch_handler.run_launch)

    if not getattr(
        launch_handler.chart_to_string,
        "_balloon_frontier_capture_tutorial_trajectory",
        False,
    ):
        launch_handler.chart_to_string = _capture_trajectory(
            launch_handler.chart_to_string
        )

    if not getattr(
        launch_handler._send_results,
        "_balloon_frontier_split_tutorial_messages",
        False,
    ):
        launch_handler._send_results = _split_send_results(
            launch_handler._send_results
        )

    if not getattr(
        launch_handler._edit_results_with_optional_view,
        "_balloon_frontier_split_tutorial_messages",
        False,
    ):
        launch_handler._edit_results_with_optional_view = _split_edit_results(
            launch_handler._edit_results_with_optional_view
        )

    launch_handler._tutorial_continue_view = _build_next_action_view
    launch_handler._attach_tutorial_continue_view = _attach_next_action_prompt
