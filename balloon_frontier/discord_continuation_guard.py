"""Harden completed tutorial result delivery for real Discord interactions."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _safe_tutorial_continue_view(configurator, interaction, result):
    """Build continuation controls without mutating ``discord.Interaction``."""
    context = getattr(configurator, "_game_entry_context", None)
    if not context:
        return None

    from balloon_frontier.game_modes import GameMode

    if context.get("mode") is not GameMode.TUTORIAL:
        return None
    completed = any(
        mission.mission_id == "first_flight" and mission.completed
        for mission in result.mission_results
    )
    if not completed:
        return None

    try:
        from balloon_frontier.discord_ui.game_menu import ContinueToStoryView

        kwargs = {
            "player_id": str(interaction.user.id),
            "channel_kind": context["channel_kind"],
            "service": context["service"],
            "on_finished": context.get("on_finished"),
        }
        on_view_changed = context.get("on_view_changed")
        if on_view_changed is not None:
            kwargs["on_view_changed"] = on_view_changed
        view = ContinueToStoryView(**kwargs)

        # Mark ownership only after construction succeeds. If construction fails,
        # the launch-button compatibility fallback remains available.
        setattr(configurator, "_tutorial_continuation_handled", True)

        if on_view_changed is not None:
            try:
                on_view_changed(view)
            except Exception:
                logger.exception("Failed to register tutorial continuation view")
        return view
    except Exception:
        # Optional continuation controls must never suppress a completed report.
        logger.exception("Failed to build tutorial continuation controls")
        return None


async def _safe_attach_tutorial_continue_view(interaction, continue_view) -> bool:
    """Attach optional controls without storing flags on the interaction."""
    if continue_view is None:
        return False
    try:
        await interaction.edit_original_response(view=continue_view)
    except Exception:
        logger.warning(
            "Tutorial completed, but continuation controls could not be attached",
            exc_info=True,
        )
        return False
    return True


async def _safe_send_results(interaction, content: str) -> bool:
    """Use a follow-up when possible and fall back to the original response."""
    followup = getattr(interaction, "followup", None)
    if followup is not None and hasattr(followup, "send"):
        try:
            await followup.send(content=content)
            return True
        except Exception:
            logger.warning(
                "Discord follow-up delivery failed; editing original response",
                exc_info=True,
            )

    try:
        await interaction.edit_original_response(content=content, view=None)
        return True
    except Exception:
        logger.exception("Discord rejected both result-delivery paths")
        return False


def install_discord_continuation_guard() -> None:
    """Replace fragile Discord delivery helpers exactly once."""
    from balloon_frontier.discord_ui import launch_handler

    if getattr(
        launch_handler._tutorial_continue_view,
        "_balloon_frontier_interaction_safe",
        False,
    ):
        return

    _safe_tutorial_continue_view._balloon_frontier_interaction_safe = True
    launch_handler._tutorial_continue_view = _safe_tutorial_continue_view
    launch_handler._attach_tutorial_continue_view = (
        _safe_attach_tutorial_continue_view
    )
    launch_handler._send_results = _safe_send_results
