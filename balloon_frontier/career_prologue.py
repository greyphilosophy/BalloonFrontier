"""Discovery-oriented first-flight prologue for Story mode."""

from __future__ import annotations

import discord

from balloon_frontier.progression import PlayerRegistry
from balloon_frontier.tutorial import TutorialConfiguratorMixin, tutorial_guidance

FIRST_FLIGHT_MISSION_ID = "first_flight"

PROLOGUE_BRIEFING = (
    "📖 **Your First Flight**\n"
    "*The beginning of your balloon career*\n\n"
    "You have a few parts, an open field, and an idea that might work. Build a "
    "balloon-assisted aircraft, launch it, and see what the atmosphere teaches you.\n\n"
    "**Objective**\n"
    "Complete a controlled endurance flight and bring the aircraft back safely.\n\n"
    "There is no prescribed design. Experiment, observe the result, and improve it."
)


def needs_first_flight(player_id: str | int | None) -> bool:
    if player_id is None:
        return False
    player = PlayerRegistry.get_or_create(str(player_id))
    return FIRST_FLIGHT_MISSION_ID not in player.missions_completed


class DiscoveryFirstFlightConfiguratorMixin(TutorialConfiguratorMixin):
    """Use tutorial physics and equipment without presenting tutorial guidance."""

    def _step_content(self) -> str:
        content = super()._step_content()
        guidance = tutorial_guidance(self._current_step) + "\n\n"
        if content.startswith(guidance):
            content = content[len(guidance):]
        return PROLOGUE_BRIEFING + "\n\n" + content

    def build_buttons(self):
        super().build_buttons()
        from balloon_frontier.discord_ui.views import _OptionButton

        # Discovery mode keeps every option visually neutral. The same introductory
        # catalog and evaluator are used, but nothing reveals a recommended route.
        for item in self.children:
            if isinstance(item, _OptionButton) and item.style is discord.ButtonStyle.success:
                item.style = discord.ButtonStyle.primary
