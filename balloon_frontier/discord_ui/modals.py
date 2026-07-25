"""Balloon Frontier — Discord modals and launch button.

Manual gas mass modal, the gas mass quick-edit button, and the launch
button that delegates to ``launch_handler.run_launch()``.
"""

import logging

import discord

from balloon_frontier.discord_ui import launch_handler

logger = logging.getLogger(__name__)

# Forward reference: BalloonConfigurator is defined in configurator.py.


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
    """Modal to set the manual gas mass (kg)."""

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
                "\u274c Please enter a valid number for gas mass.",
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
            "\u2705 Manual gas mass updated.",
            ephemeral=True,
        )


class _LaunchButton(discord.ui.Button):
    """Launch button that delegates to launch_handler."""

    def __init__(self, parent, label="\U0001f680 Launch", callback=None):
        super().__init__(label=label, style=discord.ButtonStyle.success)
        self._parent = parent

    async def callback(self, interaction):
        await launch_handler.run_launch(self._parent, interaction)
