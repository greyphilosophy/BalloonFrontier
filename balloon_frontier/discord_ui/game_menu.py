"""Menu-driven Discord entry point for Balloon Frontier."""

from __future__ import annotations

from collections.abc import Callable

import discord

from balloon_frontier.balloon_cluster import (
    BalloonClusterConfiguratorMixin,
    BalloonClusterFlightService,
)
from balloon_frontier.game_modes import GameMode
from balloon_frontier.session_adapters import SessionAwareFlightService
from balloon_frontier.discord_ui.configurator import BalloonConfigurator


class _ModeButton(discord.ui.Button):
    def __init__(self, mode: GameMode, parent: "GameModeView") -> None:
        super().__init__(
            label=mode.label,
            style=discord.ButtonStyle.primary,
            custom_id=f"game_mode_{mode.value}",
        )
        self.mode = mode
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.parent_view.select_mode(interaction, self.mode)


class GameModeView(discord.ui.View):
    """First screen shown after any message from an idle player."""

    def __init__(
        self,
        *,
        player_id: str | int,
        channel_kind: str,
        service,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(timeout=300)
        self.player_id = str(player_id)
        self.channel_kind = channel_kind
        self.service = service
        self.on_finished = on_finished
        self._msg = None
        for mode in GameMode:
            self.add_item(_ModeButton(mode, self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return bool(interaction.user and str(interaction.user.id) == self.player_id)

    async def select_mode(self, interaction: discord.Interaction, mode: GameMode) -> None:
        session_service = SessionAwareFlightService(
            self.service,
            mode=mode,
            ui="discord",
            channel_kind=self.channel_kind,
            on_finished=self.on_finished,
        )
        wrapped = BalloonClusterFlightService(session_service)

        configurator_mixins = [BalloonClusterConfiguratorMixin]
        if mode is GameMode.TUTORIAL:
            from balloon_frontier.tutorial import TutorialConfiguratorMixin
            from balloon_frontier.tutorial_catalog import ensure_discord_tutorial_options

            ensure_discord_tutorial_options()
            configurator_mixins.insert(0, TutorialConfiguratorMixin)

        configurator_type = type(
            "BalloonFrontierConfigurator",
            tuple(configurator_mixins) + (BalloonConfigurator,),
            {},
        )
        configurator = configurator_type(service=wrapped)
        configurator._msg = interaction.message
        await interaction.response.edit_message(
            content=configurator._step_content(),
            view=configurator,
        )


def game_mode_prompt() -> str:
    return (
        "🎈 **Balloon Frontier**\n\n"
        "Choose how you want to play. After this, the game is controlled through menus and buttons."
    )
