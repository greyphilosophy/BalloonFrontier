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
    def __init__(
        self,
        mode: GameMode,
        parent: "GameModeView",
        *,
        tutorial_complete: bool,
    ) -> None:
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


async def _configurator_interaction_check(
    configurator: BalloonConfigurator,
    interaction: discord.Interaction,
) -> bool:
    """Keep every step of a game session bound to its originating player."""
    context = getattr(configurator, "_game_entry_context", None)
    player_id = context.get("player_id") if context else None
    return bool(
        player_id is not None
        and interaction.user
        and str(interaction.user.id) == str(player_id)
    )


def _configurator_get_player_state(configurator: BalloonConfigurator):
    """Read progression for the player bound to this game session."""
    context = getattr(configurator, "_game_entry_context", None)
    player_id = context.get("player_id") if context else None
    if player_id is None:
        return None
    return PlayerRegistry.get_or_create(str(player_id))


def _configurator_for_mode(
    *,
    service,
    mode: GameMode,
    player_id: str,
    channel_kind: str,
    on_finished: Callable[[], None] | None,
    on_view_changed: Callable[[discord.ui.View], None] | None = None,
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
    hidden_story_prologue = False
    if mode is GameMode.TUTORIAL:
        from balloon_frontier.tutorial import TutorialConfiguratorMixin
        from balloon_frontier.tutorial_catalog import ensure_discord_tutorial_options

        ensure_discord_tutorial_options()
        if supports_wizard_mixins:
            configurator_mixins.insert(0, TutorialConfiguratorMixin)
    elif mode is GameMode.STORY and supports_wizard_mixins:
        from balloon_frontier.career_prologue import (
            DiscoveryFirstFlightConfiguratorMixin,
            DiscoveryFirstFlightService,
            needs_first_flight,
        )

        hidden_story_prologue = needs_first_flight(player_id)
        if hidden_story_prologue:
            from balloon_frontier.tutorial_catalog import ensure_discord_tutorial_options

            ensure_discord_tutorial_options()
            wrapped.service = DiscoveryFirstFlightService(wrapped.service)
            configurator_mixins.insert(0, DiscoveryFirstFlightConfiguratorMixin)
        else:
            from balloon_frontier.story import StoryConfiguratorMixin

            configurator_mixins.insert(0, StoryConfiguratorMixin)

    configurator_type = type(
        "BalloonFrontierConfigurator",
        tuple(configurator_mixins) + (BalloonConfigurator,),
        {
            "interaction_check": _configurator_interaction_check,
            "_get_player_state": _configurator_get_player_state,
        },
    )

    configurator = configurator_type(service=wrapped)
    configurator.timeout = None
    configurator._game_entry_context = {
        "service": service,
        "mode": GameMode.TUTORIAL if hidden_story_prologue else mode,
        "requested_mode": mode,
        "hidden_story_prologue": hidden_story_prologue,
        "player_id": player_id,
        "channel_kind": channel_kind,
        "on_finished": on_finished,
        "on_view_changed": on_view_changed,
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
    on_view_changed: Callable[[discord.ui.View], None] | None = None,
) -> None:
    configurator = _configurator_for_mode(
        service=service,
        mode=mode,
        player_id=player_id,
        channel_kind=channel_kind,
        on_finished=on_finished,
        on_view_changed=on_view_changed,
    )
    configurator._msg = interaction.message
    await interaction.response.edit_message(
        content=configurator._step_content(),
        view=configurator,
    )
    if on_view_changed is not None:
        on_view_changed(configurator)


def _start_mode_kwargs(
    *,
    service,
    mode: GameMode,
    player_id: str,
    channel_kind: str,
    on_finished: Callable[[], None] | None,
    on_view_changed: Callable[[discord.ui.View], None] | None,
) -> dict:
    """Build start-mode kwargs without adding optional compatibility noise."""
    kwargs = {
        "service": service,
        "mode": mode,
        "player_id": player_id,
        "channel_kind": channel_kind,
        "on_finished": on_finished,
    }
    if on_view_changed is not None:
        kwargs["on_view_changed"] = on_view_changed
    return kwargs


class GameModeView(discord.ui.View):
    def __init__(
        self,
        *,
        player_id: str | int,
        channel_kind: str,
        service,
        on_finished: Callable[[], None] | None = None,
        on_view_changed: Callable[[discord.ui.View], None] | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self.player_id = str(player_id)
        self.channel_kind = channel_kind
        self.service = service
        self.on_finished = on_finished
        self.on_view_changed = on_view_changed
        self._msg = None

        player = PlayerRegistry.get_or_create(self.player_id)
        tutorial_complete = "first_flight" in player.missions_completed
        for mode in GameMode:
            self.add_item(
                _ModeButton(
                    mode,
                    self,
                    tutorial_complete=tutorial_complete,
                )
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return bool(interaction.user and str(interaction.user.id) == self.player_id)

    async def select_mode(self, interaction: discord.Interaction, mode: GameMode) -> None:
        await start_mode(
            interaction,
            **_start_mode_kwargs(
                service=self.service,
                mode=mode,
                player_id=self.player_id,
                channel_kind=self.channel_kind,
                on_finished=self.on_finished,
                on_view_changed=self.on_view_changed,
            ),
        )


class _ContinueToStoryButton(discord.ui.Button):
    def __init__(self, parent: "ContinueToStoryView") -> None:
        super().__init__(
            label="Continue Career",
            style=discord.ButtonStyle.success,
            custom_id="continue_to_story",
        )
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        await start_mode(
            interaction,
            **_start_mode_kwargs(
                service=self.parent_view.service,
                mode=GameMode.STORY,
                player_id=self.parent_view.player_id,
                channel_kind=self.parent_view.channel_kind,
                on_finished=self.parent_view.on_finished,
                on_view_changed=self.parent_view.on_view_changed,
            ),
        )


class ContinueToStoryView(discord.ui.View):
    """One-click handoff from the completed first flight into the career."""

    def __init__(
        self,
        *,
        player_id: str | int,
        channel_kind: str,
        service,
        on_finished: Callable[[], None] | None = None,
        on_view_changed: Callable[[discord.ui.View], None] | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self.player_id = str(player_id)
        self.channel_kind = channel_kind
        self.service = service
        self.on_finished = on_finished
        self.on_view_changed = on_view_changed
        self._resume_content = (
            "🎈 **First Flight Complete**\n\n"
            "Your progress is saved. Continue your balloon career when you are ready."
        )
        self.add_item(_ContinueToStoryButton(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return bool(interaction.user and str(interaction.user.id) == self.player_id)


def game_mode_prompt() -> str:
    return (
        "🎈 **Balloon Frontier**\n\n"
        "Choose how you want to play. After this, the game is controlled through menus and buttons."
    )
