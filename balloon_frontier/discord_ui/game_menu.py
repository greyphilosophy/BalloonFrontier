"""Menu-driven Discord entry point for Balloon Frontier."""

from __future__ import annotations

from collections.abc import Callable

import discord

from balloon_frontier.balloon_cluster import (
    BalloonClusterConfiguratorMixin,
    BalloonClusterFlightService,
)
from balloon_frontier.game_modes import GameMode, list_game_modes
from balloon_frontier.how_to_play import how_to_play_text
from balloon_frontier.progression import PlayerRegistry
from balloon_frontier.session_adapters import SessionAwareFlightService
from balloon_frontier.story_mission_select import (
    StoryMissionChoice,
    resolve_story_mission,
    story_mission_choices,
)
from balloon_frontier.discord_ui.configurator import BalloonConfigurator
from balloon_frontier.discord_ui.payload_feedback import (
    PayloadFeedbackConfiguratorMixin,
)


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


class _HowToPlayButton(discord.ui.Button):
    def __init__(self, parent: "GameModeView") -> None:
        super().__init__(
            label="How to Play",
            style=discord.ButtonStyle.secondary,
            custom_id="how_to_play",
        )
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.parent_view.show_how_to_play(interaction)


class _BackToModesButton(discord.ui.Button):
    def __init__(self, parent) -> None:
        super().__init__(
            label="Back to Modes",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{type(parent).__name__.lower()}_back_to_modes",
        )
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        await show_game_mode_menu(
            interaction,
            player_id=self.parent_view.player_id,
            channel_kind=self.parent_view.channel_kind,
            service=self.parent_view.service,
            on_finished=self.parent_view.on_finished,
            on_view_changed=self.parent_view.on_view_changed,
        )


class HowToPlayView(discord.ui.View):
    """Static instructions that do not create a simulation session."""

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
        self._resume_content = how_to_play_text()
        self.add_item(_BackToModesButton(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return bool(interaction.user and str(interaction.user.id) == self.player_id)


class _StoryMissionButton(discord.ui.Button):
    def __init__(self, choice: StoryMissionChoice, parent: "StoryMissionSelectView") -> None:
        status = "Replay" if choice.completed else "Next"
        style = (
            discord.ButtonStyle.secondary
            if choice.completed
            else discord.ButtonStyle.success
        )
        super().__init__(
            label=f"{status}: {choice.chapter.title}",
            style=style,
            custom_id=f"story_mission_{choice.mission_id}",
        )
        self.mission_id = choice.mission_id
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.parent_view.select_mission(interaction, self.mission_id)


class StoryMissionSelectView(discord.ui.View):
    """Show completed Story missions plus the next unlocked mission."""

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
        self.choices = story_mission_choices(self.player_id)
        self._resume_content = story_mission_select_prompt(self.player_id)

        for choice in self.choices:
            self.add_item(_StoryMissionButton(choice, self))
        self.add_item(_BackToModesButton(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return bool(interaction.user and str(interaction.user.id) == self.player_id)

    async def select_mission(
        self,
        interaction: discord.Interaction,
        mission_id: str,
    ) -> None:
        await start_mode(
            interaction,
            **_start_mode_kwargs(
                service=self.service,
                mode=GameMode.STORY,
                player_id=self.player_id,
                channel_kind=self.channel_kind,
                on_finished=self.on_finished,
                on_view_changed=self.on_view_changed,
                story_mission_id=mission_id,
            ),
        )


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


async def _configurator_on_back(
    configurator: BalloonConfigurator,
    interaction: discord.Interaction,
) -> None:
    """Navigate within configuration, or leave step 1 for its parent menu."""

    if configurator._prev_step():
        configurator.build_buttons()
        await configurator._send_step(interaction)
        return

    context = getattr(configurator, "_game_entry_context", None) or {}
    mode = context.get("mode")
    if mode is GameMode.STORY:
        await show_story_mission_select(
            interaction,
            player_id=context["player_id"],
            channel_kind=context["channel_kind"],
            service=context["service"],
            on_finished=context.get("on_finished"),
            on_view_changed=context.get("on_view_changed"),
        )
        return

    await show_game_mode_menu(
        interaction,
        player_id=context.get("player_id", ""),
        channel_kind=context.get("channel_kind", "dm"),
        service=context.get("service"),
        on_finished=context.get("on_finished"),
        on_view_changed=context.get("on_view_changed"),
    )


def _configurator_for_mode(
    *,
    service,
    mode: GameMode,
    player_id: str,
    channel_kind: str,
    on_finished: Callable[[], None] | None,
    on_view_changed: Callable[[discord.ui.View], None] | None = None,
    story_mission_id: str | None = None,
):
    # Old callers may still pass the removed Tutorial mode. Treat it as Story;
    # there is no separate tutorial session or simulation path anymore.
    if mode is GameMode.TUTORIAL:
        mode = GameMode.STORY

    selected_story_mission_id = None
    if mode is GameMode.STORY:
        selected_story_mission_id = resolve_story_mission(
            player_id,
            story_mission_id,
        )

    session_service = SessionAwareFlightService(
        service,
        mode=mode,
        ui="discord",
        channel_kind=channel_kind,
        on_finished=on_finished,
        story_player_id=player_id,
        story_mission_id=selected_story_mission_id,
    )
    wrapped = BalloonClusterFlightService(session_service)

    supports_wizard_mixins = all(
        hasattr(BalloonConfigurator, name)
        for name in ("build_buttons", "_compute_gas_mass", "_build_config_text")
    )
    configurator_mixins = (
        [PayloadFeedbackConfiguratorMixin, BalloonClusterConfiguratorMixin]
        if supports_wizard_mixins
        else []
    )

    first_flight = False
    if mode is GameMode.STORY and supports_wizard_mixins:
        from balloon_frontier.career_prologue import DiscoveryFirstFlightConfiguratorMixin
        from balloon_frontier.story import FIRST_FLIGHT_MISSION_ID, StoryConfiguratorMixin

        first_flight = selected_story_mission_id == FIRST_FLIGHT_MISSION_ID
        if first_flight:
            # Limit the menu only. The service, weather, evaluator, and physics are
            # the same Story path used after onboarding.
            configurator_mixins.insert(1, DiscoveryFirstFlightConfiguratorMixin)
        else:
            configurator_mixins.insert(1, StoryConfiguratorMixin)

    configurator_type = type(
        "BalloonFrontierConfigurator",
        tuple(configurator_mixins) + (BalloonConfigurator,),
        {
            "interaction_check": _configurator_interaction_check,
            "_get_player_state": _configurator_get_player_state,
            "_on_back": _configurator_on_back,
        },
    )

    configurator = configurator_type(service=wrapped)
    configurator.timeout = None
    configurator._game_entry_context = {
        "service": service,
        "mode": mode,
        "player_id": player_id,
        "channel_kind": channel_kind,
        "on_finished": on_finished,
        "on_view_changed": on_view_changed,
        "first_flight": first_flight,
        "story_mission_id": selected_story_mission_id,
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
    story_mission_id: str | None = None,
) -> None:
    configurator = _configurator_for_mode(
        service=service,
        mode=mode,
        player_id=player_id,
        channel_kind=channel_kind,
        on_finished=on_finished,
        on_view_changed=on_view_changed,
        story_mission_id=story_mission_id,
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
    story_mission_id: str | None = None,
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
    if story_mission_id is not None:
        kwargs["story_mission_id"] = story_mission_id
    return kwargs


async def show_game_mode_menu(
    interaction: discord.Interaction,
    *,
    player_id: str | int,
    channel_kind: str,
    service,
    on_finished: Callable[[], None] | None = None,
    on_view_changed: Callable[[discord.ui.View], None] | None = None,
) -> None:
    view = GameModeView(
        player_id=player_id,
        channel_kind=channel_kind,
        service=service,
        on_finished=on_finished,
        on_view_changed=on_view_changed,
    )
    await interaction.response.edit_message(content=game_mode_prompt(), view=view)
    if on_view_changed is not None:
        on_view_changed(view)


async def show_story_mission_select(
    interaction: discord.Interaction,
    *,
    player_id: str | int,
    channel_kind: str,
    service,
    on_finished: Callable[[], None] | None = None,
    on_view_changed: Callable[[discord.ui.View], None] | None = None,
) -> None:
    view = StoryMissionSelectView(
        player_id=player_id,
        channel_kind=channel_kind,
        service=service,
        on_finished=on_finished,
        on_view_changed=on_view_changed,
    )
    await interaction.response.edit_message(
        content=view._resume_content,
        view=view,
    )
    if on_view_changed is not None:
        on_view_changed(view)


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

        self.add_item(_HowToPlayButton(self))
        for mode in list_game_modes():
            self.add_item(_ModeButton(mode, self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return bool(interaction.user and str(interaction.user.id) == self.player_id)

    async def show_how_to_play(self, interaction: discord.Interaction) -> None:
        view = HowToPlayView(
            player_id=self.player_id,
            channel_kind=self.channel_kind,
            service=self.service,
            on_finished=self.on_finished,
            on_view_changed=self.on_view_changed,
        )
        await interaction.response.edit_message(content=how_to_play_text(), view=view)
        if self.on_view_changed is not None:
            self.on_view_changed(view)

    async def select_mode(self, interaction: discord.Interaction, mode: GameMode) -> None:
        if mode is GameMode.STORY:
            await show_story_mission_select(
                interaction,
                player_id=self.player_id,
                channel_kind=self.channel_kind,
                service=self.service,
                on_finished=self.on_finished,
                on_view_changed=self.on_view_changed,
            )
            return

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
            label="Continue Story",
            style=discord.ButtonStyle.success,
            custom_id="continue_to_story",
        )
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        await show_story_mission_select(
            interaction,
            player_id=self.parent_view.player_id,
            channel_kind=self.parent_view.channel_kind,
            service=self.parent_view.service,
            on_finished=self.parent_view.on_finished,
            on_view_changed=self.parent_view.on_view_changed,
        )


class ContinueToStoryView(discord.ui.View):
    """Advance from a completed first flight to Story Mission Select."""

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
            "Your progress is saved. Continue to Story Mission Select when you are ready."
        )
        self.add_item(_ContinueToStoryButton(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return bool(interaction.user and str(interaction.user.id) == self.player_id)


def story_mission_select_prompt(player_id: str | int) -> str:
    choices = story_mission_choices(player_id)
    lines = [
        "📖 **Story Missions**",
        "",
        "Replay any completed mission, or continue with your next unlocked mission.",
        "",
    ]
    for choice in choices:
        status = "✅ Completed — replay available" if choice.completed else "▶ Next mission"
        lines.append(f"**{choice.chapter.title}** — {status}")
        lines.append(f"*{choice.chapter.season}*")
    if choices and all(choice.completed for choice in choices):
        lines.extend(("", "All currently available Story missions are complete."))
    return "\n".join(lines)


def game_mode_prompt() -> str:
    return (
        "🎈 **Balloon Frontier**\n\n"
        "Choose **How to Play** for instructions, or start Story, Scenario, or Free Play. "
        "Story opens Mission Select so you can continue or replay completed missions."
    )
