"""Shared content and outcome rules for the Balloon Frontier tutorial."""

from __future__ import annotations

from dataclasses import dataclass, replace

from balloon_frontier.flight_service import FlightOutcome
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import MissionResult
from balloon_frontier.tutorial_catalog import (
    QUADCOPTER,
    TUTORIAL_ASSIST_ENVELOPE,
)


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
        "Review the design and launch it. The result will explain what happened, which design risks applied, and what to try next.",
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
    hint = (
        "\n\nGreen buttons show the suggested first route; other available choices remain selectable."
        if step < 5
        else ""
    )
    return f"🎓 **{info.title}**\n{info.prompt}{hint}"


def is_tutorial_mode(mode) -> bool:
    return mode is GameMode.TUTORIAL or mode == GameMode.TUTORIAL.value


def _observed_facts(outcome: FlightOutcome) -> tuple[list[str], list[str]]:
    result = outcome.result
    peak = float(getattr(result, "peak_altitude_m", 0.0))
    duration = float(getattr(result, "duration_s", 0.0))
    burst = bool(getattr(result, "burst", False))
    crashed = bool(getattr(result, "crashed", False))
    landed = bool(getattr(result, "landed", False))

    facts = [f"Peak altitude {peak:.0f} m; flight time {duration:.0f} s."]
    advice: list[str] = []
    if burst:
        facts.append("The balloon burst.")
        advice.append("Reduce fill or choose a configuration with more expansion margin.")
    if crashed:
        facts.append("The aircraft crashed during recovery.")
        advice.append("Improve recovery and descent control before repeating the mission.")
    elif landed:
        facts.append("The aircraft landed successfully.")
    else:
        facts.append("No landing was confirmed before the simulation ended.")
    return facts, advice


def _design_implications(request) -> tuple[list[str], list[str]]:
    risks: list[str] = []
    advice: list[str] = []
    payloads = set(request.payload_ids)
    fill_mode = getattr(request.fill_mode, "value", request.fill_mode)
    balloon_count = int(getattr(request, "balloon_count", 1))

    if request.gas_id == "hot_air":
        risks.append("Hot air offers less lift and endurance than helium for this aircraft.")
        advice.append("Use helium for the endurance route.")
    if request.envelope_id == "latex":
        risks.append("Latex is flexible, so the suspended aircraft is harder to steer precisely.")
        advice.append("Use the Mylar assist balloon for a more stable platform.")
    if "quadcopter" not in payloads:
        risks.append("Without the quadcopter there is no active steering or station keeping.")
        advice.append("Add the quadcopter to follow the course.")

    fill_lessons = {
        "light": (
            "Light fill leaves little free-lift margin.",
            "Use automatic or normal fill.",
        ),
        "heavy": (
            "Heavy fill encourages a fast climb and reduces controlled endurance time.",
            "Use automatic or normal fill.",
        ),
        "manual": (
            "Manual fill can be poorly balanced unless gas mass is calculated carefully.",
            "Start with automatic fill, then compare the required gas mass.",
        ),
    }
    if fill_mode in fill_lessons:
        risk, next_step = fill_lessons[fill_mode]
        risks.append(risk)
        advice.append(next_step)
    if balloon_count > 3:
        risks.append("More than three balloons increase drift and communications-range risk.")
        advice.append("Use three or fewer balloons for this test.")
    return risks, advice


def evaluate_tutorial_outcome(request, outcome: FlightOutcome) -> FlightOutcome:
    """Evaluate every available choice and produce a concise educational debrief."""
    facts, recovery_advice = _observed_facts(outcome)
    risks, design_advice = _design_implications(request)
    result = outcome.result
    payloads = set(request.payload_ids)
    fill_mode = getattr(request.fill_mode, "value", request.fill_mode)
    balloon_count = int(getattr(request, "balloon_count", 1))

    configuration_succeeds = (
        request.gas_id == "helium"
        and request.envelope_id == "mylar"
        and "quadcopter" in payloads
        and request.launch_site_id == "field"
        and fill_mode in {"auto", "normal"}
        and balloon_count <= 3
    )
    flight_succeeds = not bool(getattr(result, "burst", False)) and not bool(
        getattr(result, "crashed", False)
    )
    success = configuration_succeeds and flight_succeeds

    if success:
        facts.insert(0, "The aircraft completed the endurance course under control.")
        why = ["The recommended gas, assist envelope, fill, and active control worked together."]
        advice = ["Try one different choice to compare its effect."]
        reward = 500
    else:
        facts.insert(0, "The aircraft did not complete the endurance course safely.")
        why = risks or ["The observed flight or selected design did not meet the mission requirements."]
        advice = recovery_advice + design_advice
        if not advice:
            advice = ["Follow the green recommended choices and launch again."]
        reward = 0

    explanation = (
        "**What happened**\n- "
        + "\n- ".join(facts)
        + "\n**Why**\n- "
        + "\n- ".join(why)
        + "\n**Try next**\n- "
        + "\n- ".join(dict.fromkeys(advice))
    )
    mission_result = MissionResult(
        mission_id=TUTORIAL_MISSION_ID,
        completed=success,
        reward=reward,
        explanation=explanation,
    )
    return replace(outcome, mission_results=(mission_result,))


def tutorial_result_summary(outcome: FlightOutcome) -> str:
    mission = next(
        (
            item
            for item in outcome.mission_results
            if item.mission_id == TUTORIAL_MISSION_ID
        ),
        None,
    )
    if mission is None:
        return "🎓 The tutorial flight produced no mission result."
    status = "Tutorial complete" if mission.completed else "Tutorial flight failed"
    return f"🎓 **{status}**\n{mission.explanation}"


class TutorialConfiguratorMixin:
    """Add tutorial prompts and keep tutorial-only equipment out of shared menus."""

    @staticmethod
    def _tutorial_envelope_options():
        from balloon_frontier.discord_ui.configurator import ENVELOPE_OPTIONS

        options = dict(ENVELOPE_OPTIONS)
        options["mylar"] = (
            TUTORIAL_ASSIST_ENVELOPE.name,
            TUTORIAL_ASSIST_ENVELOPE.max_volume_m3,
            TUTORIAL_ASSIST_ENVELOPE.mass_kg,
            TUTORIAL_ASSIST_ENVELOPE.drag_coefficient,
            TUTORIAL_ASSIST_ENVELOPE.burst_stretch_ratio,
            TUTORIAL_ASSIST_ENVELOPE.cost,
        )
        return options

    @staticmethod
    def _tutorial_payload_options():
        from balloon_frontier.discord_ui.configurator import PAYLOAD_OPTIONS

        options = dict(PAYLOAD_OPTIONS)
        options["quadcopter"] = (
            QUADCOPTER.name,
            QUADCOPTER.mass_kg,
            QUADCOPTER.cost,
            QUADCOPTER.has_valve,
        )
        return options

    def _tutorial_options(self, step=None):
        from balloon_frontier.discord_ui.configurator import (
            FILL_MODES,
            GAS_OPTIONS,
            SITE_OPTIONS,
            _Step,
        )

        current_step = self._current_step if step is None else step
        catalogs = {
            _Step.CHOOSE_GAS: GAS_OPTIONS,
            _Step.CHOOSE_ENVELOPE: self._tutorial_envelope_options(),
            _Step.CHOOSE_FILL: FILL_MODES,
            _Step.CHOOSE_PAYLOADS: self._tutorial_payload_options(),
            _Step.CHOOSE_SITE: SITE_OPTIONS,
        }
        catalog = catalogs[current_step]
        return {key: catalog[key] for key in TUTORIAL_OPTION_KEYS[current_step]}

    def _compute_gas_mass(self):
        from balloon_frontier.fill import (
            FillMode,
            apply_fill_mode,
            calculate_max_safe_gas_mass,
        )

        gas_type = self.state["gas"]
        fill_mode = self.state["fill_mode"]
        volume = self._tutorial_envelope_options()[self.state["envelope"]][1]
        env_params = self._get_env_params()
        env_params["envelope_type"] = (
            "tutorial_mylar_assist"
            if self.state["envelope"] == "mylar"
            else self.state["envelope"]
        )
        mode = {
            "auto": FillMode.AUTO,
            "light": FillMode.LIGHT,
            "normal": FillMode.NORMAL,
            "heavy": FillMode.HEAVY,
            "manual": FillMode.MANUAL,
        }.get(fill_mode, FillMode.AUTO)
        if mode == FillMode.MANUAL:
            manual_mass = self.state.get("manual_gas_mass")
            if manual_mass is None:
                manual_mass = calculate_max_safe_gas_mass(
                    volume, gas_type, **env_params
                )
                self.state["manual_gas_mass"] = manual_mass
            mass = apply_fill_mode(
                volume,
                gas_type,
                FillMode.MANUAL,
                manual_mass_kg=manual_mass,
                **env_params,
            )
        else:
            mass = apply_fill_mode(volume, gas_type, mode, **env_params)
        return round(mass, 3)

    def _build_config_text(self):
        from balloon_frontier.discord_ui.configurator import (
            FILL_MODES,
            GAS_OPTIONS,
            SITE_OPTIONS,
        )

        state = self.state
        gas = GAS_OPTIONS[state["gas"]]
        envelope = self._tutorial_envelope_options()[state["envelope"]]
        site = SITE_OPTIONS[state["site"]]
        payloads = [self._tutorial_payload_options()[p] for p in state["payloads"]]
        gas_mass = state.get("gas_mass")
        if gas_mass is None:
            gas_mass = self._compute_gas_mass()
            state["gas_mass"] = gas_mass
        payload_mass = sum(item[1] for item in payloads)
        lines = ["🎈 **Balloon Configuration**\n"]
        lines.append(f"Gas: {gas[0]}")
        lines.append(f"Fill: {FILL_MODES[state['fill_mode']]['label']} → {gas_mass:.3f} kg")
        lines.append(f"Envelope: {envelope[0]} — {envelope[1]}m³")
        lines.append(f"Payloads: {', '.join(item[0] for item in payloads)}")
        lines.append(f"Site: {site.name}")
        lines.append(f"Total mass: {gas_mass + envelope[2] + payload_mass:.1f} kg\n")
        lines.append("Review looks good? Hit **Launch**! 🚀")
        return "\n".join(lines)

    def _step_content(self) -> str:
        from balloon_frontier.discord_ui.configurator import _Step

        if self._current_step == _Step.REVIEW_LAUNCH:
            content = super()._step_content()
        else:
            player = self._get_player_state()
            lines = [
                "🔧 **Balloon Configuration**\n",
                f"**Step {self._current_step + 1}/{len(self.STEPS)}:** "
                f"{self.STEP_LABELS[self._current_step]}\n",
            ]
            options = self._tutorial_options()
            if self._current_step == _Step.CHOOSE_GAS:
                for index, gas in enumerate(options.values(), 1):
                    lines.append(f"{index}  {gas[0]}  (ρ={gas[1]} kg/m³, ${gas[2]}/kg)")
            elif self._current_step == _Step.CHOOSE_ENVELOPE:
                for index, envelope in enumerate(options.values(), 1):
                    lines.append(f"{index}  {envelope[0]}  ({envelope[1]}m³)")
            elif self._current_step == _Step.CHOOSE_FILL:
                for index, fill in enumerate(options.values(), 1):
                    lines.append(f"{index}  {fill['label']}")
                    lines.append(f"     {fill['description']}")
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
            await interaction.response.send_message(
                "That option isn't available right now.", ephemeral=True
            )
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
            await interaction.response.send_message(
                "That option isn't available right now.", ephemeral=True
            )
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

        if (
            self._current_step in TUTORIAL_OPTION_KEYS
            and self._current_step != _Step.CHOOSE_FILL
        ):
            for item in list(self.children):
                if isinstance(item, _OptionButton):
                    self.remove_item(item)
            callback = {
                _Step.CHOOSE_GAS: self._on_gas,
                _Step.CHOOSE_ENVELOPE: self._on_envelope,
                _Step.CHOOSE_PAYLOADS: self._on_payload,
                _Step.CHOOSE_SITE: self._on_site,
            }[self._current_step]
            label = {
                _Step.CHOOSE_GAS: "Choose gas",
                _Step.CHOOSE_ENVELOPE: "Choose envelope",
                _Step.CHOOSE_PAYLOADS: "Toggle payload",
                _Step.CHOOSE_SITE: "Choose site",
            }[self._current_step]
            for index in range(1, len(self._tutorial_options()) + 1):
                self.add_item(_OptionButton(index, f"{label} {index}", callback))

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
