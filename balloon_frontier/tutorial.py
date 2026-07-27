"""Shared content and outcome rules for the Balloon Frontier tutorial."""

from __future__ import annotations

from dataclasses import dataclass, replace

from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import MissionResult


TUTORIAL_MISSION_ID = "first_flight"


@dataclass(frozen=True)
class TutorialStep:
    title: str
    prompt: str


TUTORIAL_STEPS = {
    0: TutorialStep(
        "Choose a lifting gas",
        "Select a gas. The menu includes each gas's density so you can compare the available lift.",
    ),
    1: TutorialStep(
        "Choose a balloon",
        "Select the envelope that will support the aircraft.",
    ),
    2: TutorialStep(
        "Choose a fill",
        "Select how much free lift the balloon should provide. You can also adjust how many identical balloons are used.",
    ),
    3: TutorialStep(
        "Choose the aircraft",
        "Select the vehicle that will steer and remain aloft.",
    ),
    4: TutorialStep(
        "Choose a test site",
        "Select where to perform the radio-control endurance test.",
    ),
    5: TutorialStep(
        "Review and launch",
        "Review the design and launch it. The flight result will show whether it remained controllable and in communications range.",
    ),
}


RECOMMENDED_TUTORIAL_CHOICES = {
    0: "helium",
    1: "mylar",
    2: "auto",
    3: "quadcopter",
    4: "field",
}


def tutorial_guidance(step: int) -> str:
    info = TUTORIAL_STEPS[step]
    hint = "\n\nGreen buttons show the suggested first route; other choices remain available." if step < 5 else ""
    return f"🎓 **{info.title}**\n{info.prompt}{hint}"


def is_tutorial_mode(mode) -> bool:
    return mode is GameMode.TUTORIAL or mode == GameMode.TUTORIAL.value


def evaluate_tutorial_outcome(request, outcome: FlightOutcome) -> FlightOutcome:
    """Apply the UI tutorial's simple, deterministic success condition.

    Choices are never blocked or explained in advance. The recommended route is
    highlighted, while alternative successful configurations remain discoverable.
    """

    payloads = set(request.payload_ids)
    balloon_count = int(getattr(request, "balloon_count", 1))
    success = (
        request.envelope_id == "mylar"
        and request.gas_id == "helium"
        and "quadcopter" in payloads
        and request.launch_site_id == "field"
        and balloon_count <= 3
    )

    if success:
        explanation = "The balloon-assisted quadcopter remained controllable and completed the endurance flight."
        reward = 500
    elif request.gas_id == "hydrogen" or balloon_count > 3:
        explanation = "The aircraft left communications range and was lost."
        reward = 0
    elif request.envelope_id != "mylar":
        explanation = "The aircraft could not be steered through the test course."
        reward = 0
    elif "quadcopter" not in payloads:
        explanation = "The vehicle could not maintain controlled flight."
        reward = 0
    else:
        explanation = "The endurance flight was not completed."
        reward = 0

    mission_result = MissionResult(
        mission_id=TUTORIAL_MISSION_ID,
        completed=success,
        reward=reward,
        explanation=explanation,
    )
    return replace(outcome, mission_results=(mission_result,))


def tutorial_result_summary(outcome: FlightOutcome) -> str:
    mission = next(
        (item for item in outcome.mission_results if item.mission_id == TUTORIAL_MISSION_ID),
        None,
    )
    if mission is None:
        return "🎓 The tutorial flight produced no mission result."
    status = "Tutorial complete" if mission.completed else "Tutorial flight failed"
    return f"🎓 **{status}**\n{mission.explanation}"


class TutorialConfiguratorMixin:
    """Add tutorial prompts and visually suggest a first successful route."""

    def _step_content(self) -> str:
        return tutorial_guidance(self._current_step) + "\n\n" + super()._step_content()

    async def _on_envelope(self, interaction, index: int):
        """Apply tutorial envelope choices without normal progression locks.

        Tutorial mode is the player's introduction to the configurator, so every
        choice shown by the tutorial must be usable by a brand-new player. Normal
        game modes continue to enforce their progression rules in the base class.
        """
        from balloon_frontier.discord_ui.configurator import ENVELOPE_OPTIONS

        key = self._option_by_index(index, ENVELOPE_OPTIONS)
        if key is None:
            await interaction.response.send_message(
                "That option isn't available right now.",
                ephemeral=True,
            )
            return
        self.state["envelope"] = key
        self.state["gas_mass"] = self._compute_gas_mass()
        await self._advance(interaction)

    def build_buttons(self):
        super().build_buttons()
        if self._current_step not in RECOMMENDED_TUTORIAL_CHOICES:
            return

        import discord
        from balloon_frontier.discord_ui.configurator import (
            ENVELOPE_OPTIONS,
            FILL_MODES,
            GAS_OPTIONS,
            PAYLOAD_OPTIONS,
            SITE_OPTIONS,
            _Step,
        )
        from balloon_frontier.discord_ui.views import _OptionButton

        options_by_step = {
            _Step.CHOOSE_GAS: GAS_OPTIONS,
            _Step.CHOOSE_ENVELOPE: ENVELOPE_OPTIONS,
            _Step.CHOOSE_FILL: FILL_MODES,
            _Step.CHOOSE_PAYLOADS: PAYLOAD_OPTIONS,
            _Step.CHOOSE_SITE: SITE_OPTIONS,
        }
        options = options_by_step[self._current_step]
        recommended = RECOMMENDED_TUTORIAL_CHOICES[self._current_step]
        try:
            recommended_index = list(options).index(recommended) + 1
        except ValueError:
            return

        for item in self.children:
            if isinstance(item, _OptionButton) and item._index == recommended_index:
                item.style = discord.ButtonStyle.success
                break
