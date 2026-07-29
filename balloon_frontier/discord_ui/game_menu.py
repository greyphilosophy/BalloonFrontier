"""Menu-driven Discord entry point for Balloon Frontier."""

from __future__ import annotations

from collections.abc import Callable

import discord

from balloon_frontier.balloon_cluster import (
    BalloonClusterConfiguratorMixin,
    BalloonClusterFlightService,
)
from balloon_frontier.game_modes import GameMode
from balloon_frontier.progression import PlayerRegistry
from balloon_frontier.session_adapters import SessionAwareFlightService
from balloon_frontier.discord_ui.configurator import BalloonConfigurator


class _ModeButton(discord.ui.Button):
    def __init__(self, mode: GameMode, parent: "GameModeView") -> None:
        player = PlayerRegistry.get_or_create(parent.player_id)
        tutorial_complete = "first_flight" in player.missions_completed
        label = mode.label
        if mode is GameMode.TUTORIAL and tutorial_complete:
            label = "Replay Tutorial"
        elif mode is GameMode.STORY and tutorial_complete:
            label = "Continue Story"
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=f"game_mode_{mode.value}",
        )
        self.mode = mode
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.parent_view.select_mode(interaction, self.mode)


def _configurator_for_mode(
    *,
    service,
    mode: GameMode,
    player_id: str,
    channel_kind: str,
    on_finished: Callable[[], None] | None,
):
    session_service = SessionAwareFlightService(
        service,
        mode=mode,
        ui="discord",
        channel_kind=channel_kind,
        on_finished=on_finished,
        story_player_id=player_id,
    )
    wrapped = BalloonClusterFlightService(session_service)

    supports_wizard_mixins = all(
        hasattr(BalloonConfigurator, name)
        for name in ("build_buttons", "_compute_gas_mass", "_build_config_text")
    )
    configurator_mixins = [BalloonClusterConfiguratorMixin] if supports_wizard_mixins else []
    if mode is GameMode.TUTORIAL:
        from balloon_frontier.tutorial import TutorialConfiguratorMixin
        from balloon_frontier.tutorial_catalog import ensure_discord_tutorial_options

        ensure_discord_tutorial_options()
        if supports_wizard_mixins:
            configurator_mixins.insert(0, TutorialConfiguratorMixin)
    elif mode is GameMode.STORY and supports_wizard_mixins:
        from balloon_frontier.story import StoryConfiguratorMixin

        configurator_mixins.insert(0, StoryConfiguratorMixin)

    if configurator_mixins:
        configurator_type = type(
            "BalloonFrontierConfigurator",
            tuple(configurator_mixins) + (BalloonConfigurator,),
            {},
        )
    else:
        configurator_type = BalloonConfigurator

    configurator = configurator_type(service=wrapped)
    configurator._game_entry_context = {
        "service": service,
        "mode": mode,
        "player_id": player_id,
        "channel_kind": channel_kind,
        "on_finished": on_finished,
    }
    return configurator


async def start_mode(
    interaction: discord.Interaction,
    *,
    service,
    mode: GameMode,
    player_id: str,
    channel_kind: str,
    on_finished: Callable[[], None] | None = None,
) -> None:
    configurator = _configurator_for_mode(
        service=service,
        mode=mode,
        player_id=player_id,
        channel_kind=channel_kind,
        on_finished=on_finished,
    )
    configurator._msg = interaction.message
    await interaction.response.edit_message(
        content=configurator._step_content(),
        view=configurator,
    )


class GameModeView(discord.ui.View):
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
        await start_mode(
            interaction,
            service=self.service,
            mode=mode,
            player_id=self.player_id,
            channel_kind=self.channel_kind,
            on_finished=self.on_finished,
        )


class _ContinueToStoryButton(discord.ui.Button):
    def __init__(self, parent: "ContinueToStoryView") -> None:
        super().__init__(
            label="Continue to Story Mode",
            style=discord.ButtonStyle.success,
            custom_id="continue_to_story",
        )
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        await start_mode(
            interaction,
            service=self.parent_view.service,
            mode=GameMode.STORY,
            player_id=self.parent_view.player_id,
            channel_kind=self.parent_view.channel_kind,
            on_finished=self.parent_view.on_finished,
        )


class ContinueToStoryView(discord.ui.View):
    """One-click handoff from a completed tutorial into Chapter 1."""

    def __init__(
        self,
        *,
        player_id: str | int,
        channel_kind: str,
        service,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(timeout=600)
        self.player_id = str(player_id)
        self.channel_kind = channel_kind
        self.service = service
        self.on_finished = on_finished
        self.add_item(_ContinueToStoryButton(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return bool(interaction.user and str(interaction.user.id) == self.player_id)


def game_mode_prompt() -> str:
    return (
        "🎈 **Balloon Frontier**\n\n"
        "Choose how you want to play. After this, the game is controlled through menus and buttons."
    )
