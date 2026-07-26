"""Shared guidance and Discord UI for the Your First Flight tutorial."""

from __future__ import annotations

from dataclasses import dataclass

from balloon_frontier.game_modes import GameMode


@dataclass(frozen=True)
class TutorialStep:
    title: str
    lesson: str
    recommendation: str


TUTORIAL_STEPS = {
    0: TutorialStep(
        "Choose a lifting gas",
        "A lifting gas is less dense than the surrounding air, so buoyancy can overcome the vehicle's weight.",
        "Helium is recommended for this first flight because it is non-flammable and easy to handle.",
    ),
    1: TutorialStep(
        "Choose an envelope",
        "The envelope contains the lifting gas. Latex weather balloons expand as outside pressure falls.",
        "Use the standard latex weather balloon for this training flight.",
    ),
    2: TutorialStep(
        "Choose a fill",
        "More gas increases free lift and ascent rate, but excessive fill can make the balloon burst earlier.",
        "Auto fill calculates a safe introductory amount.",
    ),
    3: TutorialStep(
        "Choose a payload",
        "Every payload adds useful capability and additional mass. More mass requires more lift.",
        "Carry the camera so the flight produces its first useful observation.",
    ),
    4: TutorialStep(
        "Choose a launch site",
        "Altitude, temperature, and wind at the launch site change the balloon's initial conditions.",
        "The open field is the safest and simplest place to begin.",
    ),
    5: TutorialStep(
        "Review and launch",
        "The normal simulator, scoring system, weather, and mission evaluator will judge this flight.",
        "Check the configuration, then launch when ready.",
    ),
}


def tutorial_guidance(step: int) -> str:
    info = TUTORIAL_STEPS[step]
    return f"🎓 **{info.title}**\n{info.lesson}\n\n💡 {info.recommendation}"


def tutorial_result_summary(outcome) -> str:
    """Explain the important results of a completed tutorial flight."""
    result = outcome.result
    mission_passed = any(
        item.mission_id == "first_flight" and item.completed
        for item in outcome.mission_results
    )
    status = "Tutorial complete!" if mission_passed else "Good first attempt — adjust the design and try again."
    return (
        f"🎓 **{status}**\n"
        f"Peak altitude: {result.peak_altitude_m:.0f} m\n"
        f"Flight time: {result.duration_s:.0f} s\n"
        f"Score: {outcome.score:.0f}\n\n"
        "Peak altitude shows how high the design climbed. Flight time shows how long it remained airborne. "
        "The mission result confirms whether the camera flight met the training objectives."
    )


def is_tutorial_mode(mode) -> bool:
    return mode is GameMode.TUTORIAL or mode == GameMode.TUTORIAL.value


class TutorialConfiguratorMixin:
    """Guided constraints layered over the normal Discord configurator."""

    def _step_content(self) -> str:
        return tutorial_guidance(self._current_step) + "\n\n" + super()._step_content()

    async def _on_envelope(self, interaction, index: int):
        from balloon_frontier.discord_ui.configurator import ENVELOPE_OPTIONS
        key = list(ENVELOPE_OPTIONS)[index - 1] if 0 < index <= len(ENVELOPE_OPTIONS) else None
        if key != "latex":
            await interaction.response.send_message(
                "🎓 The training flight uses the standard latex weather balloon.",
                ephemeral=True,
            )
            return
        await super()._on_envelope(interaction, index)

    async def _on_fill(self, interaction, index: int):
        from balloon_frontier.discord_ui.configurator import FILL_MODES
        key = list(FILL_MODES)[index - 1] if 0 < index <= len(FILL_MODES) else None
        if key != "auto":
            await interaction.response.send_message(
                "🎓 Use Auto fill for the first flight; you can experiment with other fills later.",
                ephemeral=True,
            )
            return
        await super()._on_fill(interaction, index)

    async def _on_payload(self, interaction, index: int):
        from balloon_frontier.discord_ui.configurator import PAYLOAD_OPTIONS
        key = list(PAYLOAD_OPTIONS)[index - 1] if 0 < index <= len(PAYLOAD_OPTIONS) else None
        if key != "camera":
            await interaction.response.send_message(
                "🎓 Select the camera for this mission. Payload experiments come after training.",
                ephemeral=True,
            )
            return
        self.state["payloads"] = ["camera"]
        self.state["gas_mass"] = self._compute_gas_mass()
        self.build_buttons()
        await self._send_step(interaction)

    async def _on_site(self, interaction, index: int):
        from balloon_frontier.discord_ui.configurator import SITE_OPTIONS
        key = list(SITE_OPTIONS)[index - 1] if 0 < index <= len(SITE_OPTIONS) else None
        if key != "field":
            await interaction.response.send_message(
                "🎓 Launch the training flight from the open field.",
                ephemeral=True,
            )
            return
        await super()._on_site(interaction, index)

    async def _advance(self, interaction):
        from balloon_frontier.discord_ui.configurator import _Step
        if self._current_step == _Step.CHOOSE_PAYLOADS and "camera" not in self.state["payloads"]:
            await interaction.response.send_message(
                "🎓 Add the camera before continuing.",
                ephemeral=True,
            )
            return
        await super()._advance(interaction)
