"""Balloon Frontier — Discord UI button views.

Numbered option buttons, back navigation, and next-step buttons used by
the BalloonConfigurator wizard.
"""

import discord

# Forward reference: BalloonConfigurator is defined in configurator.py.
# We use a string type hint to avoid circular imports.


class _OptionButton(discord.ui.Button):
    """A numbered option button. Callback is a function on the bot client."""

    def __init__(self, index: int, style_label: str, callback_factory):
        super().__init__(
            label=style_label,
            style=discord.ButtonStyle.primary,
            custom_id=f"cfg_option_{index}",
        )
        self._index = index
        self._callback = callback_factory

    async def callback(self, interaction: discord.Interaction):
        await self._callback(interaction, self._index)


class _BackButton(discord.ui.Button):
    """Back button present on every step except the first."""

    def __init__(self, parent: "BalloonConfigurator"):  # type: ignore[name-defined]
        super().__init__(
            label="\u25c0 Back",
            style=discord.ButtonStyle.secondary,
            custom_id="cfg_back",
        )
        self._parent = parent

    async def callback(self, interaction: discord.Interaction):
        await self._parent._on_back(interaction)


class _NextButton(discord.ui.Button):
    """Button that advances to the next walkthrough step."""

    def __init__(self, parent: "BalloonConfigurator"):  # type: ignore[name-defined]
        super().__init__(
            label="Next \u25b6",
            style=discord.ButtonStyle.success,
            custom_id="cfg_next",
        )
        self._parent = parent

    async def callback(self, interaction: discord.Interaction):
        await self._parent._advance(interaction)
