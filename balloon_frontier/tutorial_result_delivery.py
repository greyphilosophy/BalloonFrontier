"""Deliver tutorial results across Discord messages with explicit next actions."""

from __future__ import annotations

from contextvars import ContextVar
from functools import wraps

import discord

from balloon_frontier.game_modes import GameMode

_TRAJECTORY_SENTINEL = "[[BALLOON_FRONTIER_TRAJECTORY_MESSAGE]]"
_split_delivery_active: ContextVar[bool] = ContextVar(
    "balloon_frontier_split_delivery_active",
    default=False,
)
_captured_trajectory: ContextVar[str | None] = ContextVar(
    "balloon_frontier_captured_trajectory",
    default=None,
)


class _TutorialActionButton(discord.ui.Button):
    def __init__(self, parent: "TutorialNextActionView", mode: GameMode) -> None:
        label = "Replay Tutorial" if mode is GameMode.TUTORIAL else "Continue Story"
        style = (
            discord.ButtonStyle.primary
            if mode is GameMode.TUTORIAL
            else discord.ButtonStyle.success
        )
        super().__init__(
            label=label,
            style=style,
            custom_id=f"tutorial_next_{mode.value}",
        )
        self.parent_view = parent
        self.mode = mode

    async def callback(self, interaction: discord.Interaction) -> None:
        from balloon_frontier.discord_ui.game_menu import start_mode

        kwargs = {
            "service": self.parent_view.service,
            "mode": self.mode,
            "player_id": self.parent_view.player_id,
            "channel_kind": self.parent_view.channel_kind,
            "on_finished": self.parent_view.on_finished,
        }
        if self.parent_view.on_view_changed is not None:
            kwargs["on_view_changed"] = self.parent_view.on_view_changed
        await start_mode(interaction, **kwargs)


class TutorialNextActionView(discord.ui.View):
    """Offer both replay and story continuation after the tutorial flight."""

    def __init__(
        self,
        *,
        player_id: str | int,
        channel_kind: str,
        service,
        on_finished=None,
        on_view_changed=None,
    ) -> None:
        super().__init__(timeout=None)
        self.player_id = str(player_id)
        self.channel_kind = channel_kind
        self.service = service
        self.on_finished = on_finished
        self.on_view_changed = on_view_changed
        self._resume_content = (
            "🎈 **Yearbook Flight Complete**\n\n"
            "Would you like to replay the tutorial or continue the story?"
        )
        self.add_item(_TutorialActionButton(self, GameMode.TUTORIAL))
        self.add_item(_TutorialActionButton(self, GameMode.STORY))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return bool(interaction.user and str(interaction.user.id) == self.player_id)


def _tutorial_launch_scope(original):
    @wraps(original)
    async def run(configurator, interaction, service):
        context = getattr(configurator, "_game_entry_context", None) or {}
        if context.get("mode") is not GameMode.TUTORIAL:
            return await original(configurator, interaction, service)

        active_token = _split_delivery_active.set(True)
        chart_token = _captured_trajectory.set(None)
        try:
            return await original(configurator, interaction, service)
        finally:
            _captured_trajectory.reset(chart_token)
            _split_delivery_active.reset(active_token)

    run._balloon_frontier_split_tutorial_delivery = True
    return run


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
        sent = await original(interaction, report)
        if sent:
            await _send_chart_followup(interaction, _captured_trajectory.get())
        return sent

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
            await original(interaction, report, continue_view)
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
    if context.get("mode") is not GameMode.TUTORIAL:
        return None
    completed = any(
        mission.mission_id == "first_flight" and mission.completed
        for mission in result.mission_results
    )
    if not completed:
        return None

    setattr(interaction, "_balloon_frontier_tutorial_continuation_handled", True)
    view = TutorialNextActionView(
        player_id=str(interaction.user.id),
        channel_kind=context["channel_kind"],
        service=context["service"],
        on_finished=context.get("on_finished"),
        on_view_changed=context.get("on_view_changed"),
    )
    callback = context.get("on_view_changed")
    if callback is not None:
        callback(view)
    return view


async def _attach_next_action_prompt(interaction, continue_view) -> bool:
    if continue_view is None:
        return False
    try:
        await interaction.edit_original_response(
            content=(
                "🎈 **Yearbook Flight Complete**\n\n"
                "Would you like to replay the tutorial or continue the story?"
            ),
            view=continue_view,
        )
    except Exception:
        return False
    setattr(interaction, "_balloon_frontier_tutorial_view_attached", True)
    return True


def install_tutorial_result_delivery() -> None:
    """Install split tutorial delivery and two-way completion controls."""
    from balloon_frontier.discord_ui import launch_handler

    if not getattr(
        launch_handler.run_launch,
        "_balloon_frontier_split_tutorial_delivery",
        False,
    ):
        launch_handler.run_launch = _tutorial_launch_scope(launch_handler.run_launch)

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
