"""Discovery-oriented first-flight prologue for Story mode."""

from __future__ import annotations

from dataclasses import replace

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

_DISCOVERY_DEBRIEF_REPLACEMENTS = {
    "The recommended gas, assist envelope, fill, and active control worked together.": (
        "Your gas, envelope, fill, and active-control choices worked together."
    ),
    "Follow the green recommended choices and launch again.": (
        "Try a different combination of gas, envelope, fill, and control, then launch again."
    ),
}


def needs_first_flight(player_id: str | int | None) -> bool:
    if player_id is None:
        return False
    player = PlayerRegistry.get_or_create(str(player_id))
    return FIRST_FLIGHT_MISSION_ID not in player.missions_completed


def discovery_first_flight_outcome(outcome):
    """Rewrite guided tutorial wording without changing evaluation or rewards."""
    rewritten = []
    changed = False
    for result in outcome.mission_results:
        if result.mission_id != FIRST_FLIGHT_MISSION_ID:
            rewritten.append(result)
            continue
        explanation = result.explanation
        for guided, discovery in _DISCOVERY_DEBRIEF_REPLACEMENTS.items():
            explanation = explanation.replace(guided, discovery)
        rewritten.append(replace(result, explanation=explanation))
        changed = changed or explanation != result.explanation
    if not changed:
        return outcome
    return replace(outcome, mission_results=tuple(rewritten))


class DiscoveryFirstFlightService:
    """Keep the tutorial evaluator while presenting a discovery-oriented debrief."""

    def __init__(self, service) -> None:
        self.service = service

    def __getattr__(self, name):
        return getattr(self.service, name)

    def run(self, request):
        return discovery_first_flight_outcome(self.service.run(request))


class DiscoveryFirstFlightConfiguratorMixin(TutorialConfiguratorMixin):
    """Use tutorial physics and equipment without presenting tutorial guidance."""

    def _equipped_payload_summary(self) -> str:
        """Describe the current payload state in stable menu order."""
        options = self._tutorial_payload_options()
        selected = set(self.state.get("payloads") or ("none",))
        names = [
            payload[0]
            for key, payload in options.items()
            if key in selected and key != "none"
        ]
        return ", ".join(names) if names else "None"

    async def _on_payload(self, interaction, index: int):
        """Toggle a payload and identify the exact change in the refreshed message."""
        from balloon_frontier.discord_ui.configurator import _Step

        options = self._tutorial_options(_Step.CHOOSE_PAYLOADS)
        keys = list(options)
        if index < 1 or index > len(keys):
            await interaction.response.send_message(
                "That option isn't available right now.", ephemeral=True
            )
            return

        selected_key = keys[index - 1]
        selected_name = options[selected_key][0]
        current = set(self.state.get("payloads") or ("none",))
        if selected_key == "none":
            self._payload_toggle_feedback = "🧹 **Payloads cleared.**"
        elif selected_key in current:
            self._payload_toggle_feedback = f"➖ **Removed:** {selected_name}"
        else:
            self._payload_toggle_feedback = f"✅ **Added:** {selected_name}"

        await super()._on_payload(interaction, index)

    def _step_content(self) -> str:
        from balloon_frontier.discord_ui.configurator import _Step

        content = super()._step_content()
        guidance = tutorial_guidance(self._current_step) + "\n\n"
        if content.startswith(guidance):
            content = content[len(guidance):]
        if self._current_step == _Step.CHOOSE_PAYLOADS:
            feedback = getattr(self, "_payload_toggle_feedback", None)
            if feedback:
                content += f"\n\n{feedback}"
            content += (
                "\n\n**Currently equipped:** "
                f"{self._equipped_payload_summary()}"
            )
        return PROLOGUE_BRIEFING + "\n\n" + content

    def build_buttons(self):
        super().build_buttons()
        from balloon_frontier.discord_ui.views import _OptionButton

        # Discovery mode keeps every option visually neutral. The same introductory
        # catalog and evaluator are used, but nothing reveals a recommended route.
        for item in self.children:
            if (
                isinstance(item, _OptionButton)
                and item.style == discord.ButtonStyle.success
            ):
                item.style = discord.ButtonStyle.primary
