"""Balloon Frontier — Discord modals and launch button.

Manual gas mass modal, the gas mass quick-edit button, and the launch
button that delegates to ``launch_handler.run_launch()``.
"""

import logging

import discord
from balloon_frontier.discord_ui import launch_handler

logger = logging.getLogger(__name__)


class _ManualGasMassButton(discord.ui.Button):
    """Button that opens the manual gas mass modal."""

    def __init__(self, parent: "BalloonConfigurator"):  # type: ignore[name-defined]
        super().__init__(
            label="Edit Gas Mass",
            style=discord.ButtonStyle.secondary,
            custom_id="cfg_manual_mass",
        )
        self._parent = parent

    async def callback(self, interaction: discord.Interaction):
        modal = _ManualGasMassModal(self._parent)
        await interaction.response.send_modal(modal)


class _ManualGasMassModal(discord.ui.Modal):
    def __init__(self, parent: "BalloonConfigurator"):  # type: ignore[name-defined]
        super().__init__(title="Manual Gas Mass")
        self._parent = parent
        current = parent.state.get("manual_gas_mass")
        default_str = "" if current is None else str(current)
        self.mass_input = discord.ui.TextInput(
            label="Gas mass (kg)",
            placeholder="e.g. 12.5",
            default=default_str,
            required=True,
            max_length=20,
        )
        self.add_item(self.mass_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = float(str(self.mass_input.value).strip())
        except Exception:
            await interaction.response.send_message(
                "❌ Please enter a valid number for gas mass.",
                ephemeral=True,
            )
            return

        val = max(0.001, val)
        self._parent.state["manual_gas_mass"] = val
        if self._parent.state.get("fill_mode") == "manual":
            self._parent.state["gas_mass"] = self._parent._compute_gas_mass()

        if getattr(self._parent, "_msg", None) is not None:
            await self._parent._msg.edit(
                content=self._parent._step_content(), view=self._parent,
            )

        await interaction.response.send_message(
            "✅ Manual gas mass updated.",
            ephemeral=True,
        )


class _LaunchButton(discord.ui.Button):
    """Launch button that delegates to launch_handler."""

    def __init__(self, parent, service: "FlightService", label: str = "🚀 Launch"):
        super().__init__(label=label, style=discord.ButtonStyle.success)
        self._parent = parent
        self._service = service

    async def callback(self, interaction):
        outcome = await launch_handler.run_launch(
            self._parent,
            interaction,
            service=self._service,
        )

        context = getattr(self._parent, "_game_entry_context", None)
        if not context or outcome is None:
            return

        from balloon_frontier.game_modes import GameMode

        if context.get("mode") is not GameMode.STORY:
            return

        mission_id = context.get("story_mission_id")
        if not mission_id and context.get("first_flight"):
            mission_id = "first_flight"
        if not mission_id:
            return

        mission_result = next(
            (
                result
                for result in outcome.mission_results
                if result.mission_id == mission_id
            ),
            None,
        )
        if mission_result is None:
            return

        # A successful first flight is already handled by the specialized split
        # result-delivery path. Failed first flights and all later Story attempts
        # still need a stable route back to Mission Select.
        if (
            context.get("first_flight")
            and mission_result.completed
            and getattr(self._parent, "_tutorial_continuation_handled", False)
        ):
            return

        continuation_attached = getattr(
            interaction,
            "_balloon_frontier_tutorial_view_attached",
            False,
        )

        try:
            player_id = str(interaction.user.id)
            from balloon_frontier.discord_ui.game_menu import ContinueToStoryView
            from balloon_frontier.story_mission_select import story_chapter_for_mission

            kwargs = {
                "player_id": player_id,
                "channel_kind": context["channel_kind"],
                "service": context["service"],
                "on_finished": context.get("on_finished"),
            }
            on_view_changed = context.get("on_view_changed")
            if on_view_changed is not None:
                kwargs["on_view_changed"] = on_view_changed
            view = ContinueToStoryView(**kwargs)
            chapter = story_chapter_for_mission(str(mission_id))
            if mission_result.completed:
                view._resume_content = (
                    f"🎈 **{chapter.title} Complete**\n\n"
                    "Your progress is saved. Return to Story Mission Select when you are ready."
                )
            else:
                view._resume_content = (
                    f"🎈 **{chapter.title} — Attempt Finished**\n\n"
                    "Return to Story Mission Select to retry this mission or replay another available mission."
                )
            if view.children and (
                not context.get("first_flight") or not mission_result.completed
            ):
                view.children[0].label = "Mission Select"

            if not continuation_attached:
                await interaction.edit_original_response(view=view)
            self._parent._tutorial_continuation_handled = True
            if on_view_changed is not None:
                on_view_changed(view)
        except Exception:
            # The flight and report already succeeded. Optional navigation must
            # never turn a completed attempt into another callback error.
            logger.warning(
                "Could not attach Story mission continuation fallback",
                exc_info=True,
            )
