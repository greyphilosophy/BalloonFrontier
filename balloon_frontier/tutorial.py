"""Shared content and outcome rules for the Balloon Frontier tutorial."""

from __future__ import annotations

from dataclasses import dataclass, replace

from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import MissionResult


TUTORIAL_MISSION_ID = "first_flight"
TUTORIAL_OPTION_KEYS = {
    0: ("helium", "hot_air"),
    1: ("mylar", "latex"),
    2: ("auto", "light", "normal", "heavy", "manual"),
    3: ("quadcopter", "none"),
    4: ("field",),
}


@dataclass(frozen=True)
class TutorialStep:
    title: str
    prompt: str


TUTORIAL_STEPS = {
    0: TutorialStep("Choose a lifting gas", "Select a gas. The menu includes each gas's density so you can compare the available lift."),
    1: TutorialStep("Choose a balloon", "Select the envelope that will support the aircraft."),
    2: TutorialStep("Choose a fill", "Select how much free lift the balloon should provide. You can also adjust how many identical balloons are used."),
    3: TutorialStep("Choose the aircraft", "Select the vehicle that will steer and remain aloft."),
    4: TutorialStep("Choose a test site", "Select where to perform the radio-control endurance test."),
    5: TutorialStep("Review and launch", "Review the design and launch it. The flight result will explain what happened, why, and what to try next."),
}

RECOMMENDED_TUTORIAL_CHOICES = {0: "helium", 1: "mylar", 2: "auto", 3: "quadcopter", 4: "field"}


def tutorial_guidance(step: int) -> str:
    info = TUTORIAL_STEPS[step]
    hint = "\n\nGreen buttons show the suggested first route; other available choices remain selectable." if step < 5 else ""
    return f"🎓 **{info.title}**\n{info.prompt}{hint}"


def is_tutorial_mode(mode) -> bool:
    return mode is GameMode.TUTORIAL or mode == GameMode.TUTORIAL.value


def _flight_facts(outcome: FlightOutcome) -> list[str]:
    result = outcome.result
    facts = [f"The flight reached {getattr(result, 'peak_altitude_m', 0.0):.0f} m and lasted {getattr(result, 'duration_s', 0.0):.0f} s."]
    if getattr(result, "burst", False):
        facts.append("The balloon burst during the flight.")
    if getattr(result, "crashed", False):
        facts.append("The aircraft crashed during recovery.")
    elif getattr(result, "landed", False):
        facts.append("The aircraft landed successfully.")
    else:
        facts.append("The simulation ended before a confirmed landing.")
    return facts


def _choice_lessons(request) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    advice: list[str] = []
    payloads = set(request.payload_ids)
    fill_mode = getattr(request.fill_mode, "value", request.fill_mode)
    balloon_count = int(getattr(request, "balloon_count", 1))

    if request.gas_id == "hot_air":
        reasons.append("Hot air produced less lift and endurance than helium for this small test aircraft.")
        advice.append("Use helium for the endurance route.")
    if request.envelope_id == "latex":
        reasons.append("The flexible latex envelope made the suspended aircraft harder to steer precisely.")
        advice.append("Use the Mylar envelope for a more stable test platform.")
    if "quadcopter" not in payloads:
        reasons.append("Without the quadcopter, the balloon had no active steering or station-keeping system.")
        advice.append("Add the quadcopter so the aircraft can follow the course.")

    fill_lessons = {
        "light": ("The light fill did not provide enough free lift for reliable controlled flight.", "Use automatic or normal fill to provide a healthier lift margin."),
        "heavy": ("The heavy fill created an aggressive climb and reduced the time available for controlled endurance flight.", "Use automatic or normal fill to balance climb rate and control."),
        "manual": ("Manual fill requires careful mass calculation; the tutorial cannot assume the chosen mass is well balanced.", "Use automatic fill first, then experiment with manual fill after reviewing the required gas mass."),
    }
    if fill_mode in fill_lessons:
        reason, next_step = fill_lessons[fill_mode]
        reasons.append(reason)
        advice.append(next_step)
    if balloon_count > 3:
        reasons.append("Using more than three balloons increased drift and carried the aircraft beyond reliable communications range.")
        advice.append("Use three or fewer balloons for this short-range test.")
    return reasons, advice


def evaluate_tutorial_outcome(request, outcome: FlightOutcome) -> FlightOutcome:
    """Evaluate every available tutorial choice and produce an educational debrief."""
    reasons, advice = _choice_lessons(request)
    payloads = set(request.payload_ids)
    fill_mode = getattr(request.fill_mode, "value", request.fill_mode)
    balloon_count = int(getattr(request, "balloon_count", 1))
    success = (
        request.gas_id == "helium"
        and request.envelope_id == "mylar"
        and "quadcopter" in payloads
        and request.launch_site_id == "field"
        and fill_mode in {"auto", "normal"}
        and balloon_count <= 3
    )

    facts = _flight_facts(outcome)
    if success:
        facts.insert(0, "The balloon-assisted quadcopter remained controllable and completed the endurance course.")
        reasons = ["Helium, the stable Mylar envelope, a balanced fill, and active quadcopter control worked together."]
        advice = ["Try another available choice to see how each design decision changes the flight."]
        reward = 500
    else:
        facts.insert(0, "The aircraft did not complete the endurance course.")
        reward = 0
        if not reasons:
            reasons.append("The selected configuration did not provide enough controllability and endurance for the mission.")
        if not advice:
            advice.append("Follow the green recommended choices for a reliable first flight.")

    explanation = (
        "**What happened**\n- " + "\n- ".join(facts)
        + "\n**Why**\n- " + "\n- ".join(reasons)
        + "\n**Try next**\n- " + "\n- ".join(dict.fromkeys(advice))
    )
    mission_result = MissionResult(TUTORIAL_MISSION_ID, success, reward, explanation)
    return replace(outcome, mission_results=(mission_result,))


def tutorial_result_summary(outcome: FlightOutcome) -> str:
    mission = next((item for item in outcome.mission_results if item.mission_id == TUTORIAL_MISSION_ID), None)
    if mission is None:
        return "🎓 The tutorial flight produced no mission result."
    status = "Tutorial complete" if mission.completed else "Tutorial flight failed"
    return f"🎓 **{status}**\n{mission.explanation}"


class TutorialConfiguratorMixin:
    """Add tutorial prompts and expose only choices available in the tutorial."""

    def _tutorial_options(self, step=None):
        from balloon_frontier.discord_ui.configurator import ENVELOPE_OPTIONS, FILL_MODES, GAS_OPTIONS, PAYLOAD_OPTIONS, SITE_OPTIONS, _Step
        current_step = self._current_step if step is None else step
        catalogs = {_Step.CHOOSE_GAS: GAS_OPTIONS, _Step.CHOOSE_ENVELOPE: ENVELOPE_OPTIONS, _Step.CHOOSE_FILL: FILL_MODES, _Step.CHOOSE_PAYLOADS: PAYLOAD_OPTIONS, _Step.CHOOSE_SITE: SITE_OPTIONS}
        catalog = catalogs[current_step]
        return {key: catalog[key] for key in TUTORIAL_OPTION_KEYS[current_step]}

    def _step_content(self) -> str:
        from balloon_frontier.discord_ui.configurator import _Step
        if self._current_step == _Step.REVIEW_LAUNCH:
            content = super()._step_content()
        else:
            player = self._get_player_state()
            lines = ["🔧 **Balloon Configuration**\n", f"**Step {self._current_step + 1}/{len(self.STEPS)}:** {self.STEP_LABELS[self._current_step]}\n"]
            options = self._tutorial_options()
            if self._current_step == _Step.CHOOSE_GAS:
                for index, gas in enumerate(options.values(), 1):
                    lines.append(f"{index}  {gas[0]}  (ρ={gas[1]} kg/m³, ${gas[2]}/kg)")
            elif self._current_step == _Step.CHOOSE_ENVELOPE:
                for index, envelope in enumerate(options.values(), 1):
                    lines.append(f"{index}  {envelope[0]}  ({envelope[1]}m³)")
            elif self._current_step == _Step.CHOOSE_FILL:
                for index, fill in enumerate(options.values(), 1):
                    lines.extend([f"{index}  {fill['label']}", f"     {fill['description']}"])
            elif self._current_step == _Step.CHOOSE_PAYLOADS:
                for index, payload in enumerate(options.values(), 1):
                    lines.append(f"{index}  {payload[0]}  ({payload[1]}kg, ${payload[2]})")
            elif self._current_step == _Step.CHOOSE_SITE:
                for index, site in enumerate(options.values(), 1):
                    lines.append(f"{index}  {site.name}")
                    if site.description:
                        lines.append(f"     {site.description}")
            lines.extend(["", "Click a button to select. Use < Back to go earlier."])
            if player:
                lines.append(f"⚡ You have {player.reputation} reputation and ${player.budget} budget.")
            content = "\n".join(lines)
        return tutorial_guidance(self._current_step) + "\n\n" + content

    async def _select_single_option(self, interaction, index: int, state_key: str):
        key = self._option_by_index(index, self._tutorial_options())
        if key is None:
            await interaction.response.send_message("That option isn't available right now.", ephemeral=True)
            return
        self.state[state_key] = key
        self.state["gas_mass"] = self._compute_gas_mass()
        await self._advance(interaction)

    async def _on_gas(self, interaction, index: int):
        await self._select_single_option(interaction, index, "gas")

    async def _on_envelope(self, interaction, index: int):
        await self._select_single_option(interaction, index, "envelope")

    async def _on_payload(self, interaction, index: int):
        key = self._option_by_index(index, self._tutorial_options(), multi=True)
        if key is None:
            await interaction.response.send_message("That option isn't available right now.", ephemeral=True)
            return
        self.state["gas_mass"] = self._compute_gas_mass()
        self.build_buttons()
        await self._send_step(interaction)

    async def _on_site(self, interaction, index: int):
        await self._select_single_option(interaction, index, "site")

    def build_buttons(self):
        super().build_buttons()
        import discord
        from balloon_frontier.discord_ui.configurator import _Step
        from balloon_frontier.discord_ui.views import _OptionButton
        if self._current_step in TUTORIAL_OPTION_KEYS and self._current_step != _Step.CHOOSE_FILL:
            for item in list(self.children):
                if isinstance(item, _OptionButton):
                    self.remove_item(item)
            callback_by_step = {_Step.CHOOSE_GAS: self._on_gas, _Step.CHOOSE_ENVELOPE: self._on_envelope, _Step.CHOOSE_PAYLOADS: self._on_payload, _Step.CHOOSE_SITE: self._on_site}
            label_by_step = {_Step.CHOOSE_GAS: "Choose gas", _Step.CHOOSE_ENVELOPE: "Choose envelope", _Step.CHOOSE_PAYLOADS: "Toggle payload", _Step.CHOOSE_SITE: "Choose site"}
            for index in range(1, len(self._tutorial_options()) + 1):
                self.add_item(_OptionButton(index, f"{label_by_step[self._current_step]} {index}", callback_by_step[self._current_step]))
        if self._current_step not in RECOMMENDED_TUTORIAL_CHOICES:
            return
        options = self._tutorial_options()
        recommended = RECOMMENDED_TUTORIAL_CHOICES[self._current_step]
        try:
            recommended_index = list(options).index(recommended) + 1
        except ValueError:
            return
        for item in self.children:
            if isinstance(item, _OptionButton) and item._index == recommended_index:
                item.style = discord.ButtonStyle.success
                break
