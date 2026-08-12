"""First-flight Story onboarding with a deliberately small configuration menu."""

from __future__ import annotations

from dataclasses import replace

from balloon_frontier.catalog import CATALOG
from balloon_frontier.fill import FillMode, apply_fill_mode


FIRST_FLIGHT_REQUIRED_PAYLOADS = ("camera", "quadcopter")
FIRST_FLIGHT_SITE_NAME = "School Athletic Field"
FIRST_FLIGHT_OPTION_KEYS = {
    0: ("helium", "air"),
    1: ("latex", "candle_kite"),
    2: ("auto", "light", "normal"),
    3: (
        "parachute",
        "candle_heater",
        "electric_heater",
        "none",
    ),
    4: ("field",),
}


def needs_first_flight(player_id: str | int | None) -> bool:
    if player_id is None:
        return False
    from balloon_frontier.progression import PlayerRegistry

    player = PlayerRegistry.get_or_create(str(player_id))
    return "first_flight" not in player.missions_completed


def _gas_option(gas_id: str) -> tuple[str, float, int]:
    gas = CATALOG.gas(gas_id)
    return gas.name, gas.molar_mass, gas.cost_per_kg


def _envelope_option(envelope_id: str) -> tuple[str, float, float, float, float, int]:
    envelope = CATALOG.envelope(envelope_id)
    return (
        envelope.name,
        envelope.max_volume_m3,
        envelope.mass_kg,
        envelope.drag_coefficient,
        envelope.burst_stretch_ratio,
        envelope.cost,
    )


def _payload_option(payload_id: str) -> tuple[str, float, int, bool]:
    if payload_id == "none":
        return "No optional payload", 0.0, 0, False
    payload = CATALOG.payload(payload_id)
    return payload.name, payload.mass_kg, payload.cost, payload.has_valve


def first_flight_site_info():
    """Return the mission-specific label over the ordinary ``field`` physics."""
    from balloon_frontier.discord_ui.configurator import SITE_OPTIONS

    return replace(
        SITE_OPTIONS["field"],
        name=FIRST_FLIGHT_SITE_NAME,
        description="School athletic field, mild crosswind",
    )


def with_required_first_flight_payloads(
    payload_ids: tuple[str, ...] | list[str],
) -> tuple[str, ...]:
    """Return required mission equipment plus deterministic optional payloads."""
    extras = tuple(
        pid
        for pid in payload_ids
        if pid not in FIRST_FLIGHT_REQUIRED_PAYLOADS and pid != "none"
    )
    deduped_extras = tuple(dict.fromkeys(extras))
    return FIRST_FLIGHT_REQUIRED_PAYLOADS + deduped_extras


def toggle_payload_selection(
    current_payloads: tuple[str, ...] | list[str],
    selected: str,
) -> tuple[str, ...]:
    """Pure deterministic payload toggle with ``none`` as the empty sentinel."""
    current = tuple(pid for pid in current_payloads if pid != "none")
    if selected == "none":
        return ("none",)
    if selected in current:
        remaining = tuple(pid for pid in current if pid != selected)
        return remaining or ("none",)
    return current + (selected,)


def toggle_first_flight_optional_payload(
    current_payloads: tuple[str, ...] | list[str],
    selected: str,
) -> tuple[str, ...]:
    """Toggle optional equipment while keeping camera and quadcopter essential."""
    optional = tuple(
        pid for pid in current_payloads if pid not in FIRST_FLIGHT_REQUIRED_PAYLOADS
    )
    toggled = toggle_payload_selection(optional, selected)
    return with_required_first_flight_payloads(toggled)


class DiscoveryFirstFlightConfiguratorMixin:
    """Expose a small Story menu while using the ordinary simulation physics.

    First Flight creates local option views from canonical definitions; it never
    mutates process-wide Discord option dictionaries. The configurator itself is
    the imperative UI shell, while option/fill transformations are deterministic.
    """

    def _first_flight_options(self, step=None):
        from balloon_frontier.discord_ui.configurator import (
            FILL_MODES,
            _Step,
        )

        current_step = self._current_step if step is None else step
        keys = FIRST_FLIGHT_OPTION_KEYS[current_step]
        if current_step == _Step.CHOOSE_GAS:
            return {key: _gas_option(key) for key in keys}
        if current_step == _Step.CHOOSE_ENVELOPE:
            return {key: _envelope_option(key) for key in keys}
        if current_step == _Step.CHOOSE_PAYLOADS:
            return {key: _payload_option(key) for key in keys}
        if current_step == _Step.CHOOSE_FILL:
            return {key: FILL_MODES[key] for key in keys}
        if current_step == _Step.CHOOSE_SITE:
            return {"field": first_flight_site_info()}
        return {}

    def _compute_gas_mass(self):
        """Compute fill with the same shared fill equations as the base wizard."""
        from balloon_frontier.discord_ui.configurator import SITE_OPTIONS

        state = self.state
        envelope = CATALOG.envelope(state["envelope"])
        site_conditions = SITE_OPTIONS[state["site"]].derive_conditions()
        mode = FillMode(state.get("fill_mode", "auto"))
        mass = apply_fill_mode(
            envelope.max_volume_m3,
            state["gas"],
            mode,
            manual_mass_kg=state.get("manual_gas_mass"),
            burst_stretch_ratio=envelope.burst_stretch_ratio,
            envelope_type=envelope.id,
            launch_altitude=site_conditions.get("launch_altitude"),
            launch_pressure=site_conditions.get("launch_pressure"),
            gas_temperature=site_conditions.get("gas_temperature"),
            safe_fill_data={
                "burst_stretch_ratio": envelope.burst_stretch_ratio,
                "safe_fill_fraction": envelope.safe_fill_fraction,
            },
        )
        return round(mass, 3)

    def _build_config_text(self):
        """Build review text without consulting or mutating global UI catalogs."""
        from balloon_frontier.discord_ui.configurator import FILL_MODES, _Step

        state = self.state
        state["payloads"] = list(
            with_required_first_flight_payloads(state.get("payloads") or ())
        )
        gas = CATALOG.gas(state["gas"])
        envelope = CATALOG.envelope(state["envelope"])
        payload_defs = [
            CATALOG.payload(pid)
            for pid in state.get("payloads") or ()
            if pid != "none"
        ]
        payload_names = [payload.name for payload in payload_defs] or ["None"]
        payload_mass = sum(payload.mass_kg for payload in payload_defs)
        gas_mass = state.get("gas_mass")
        if gas_mass is None:
            gas_mass = self._compute_gas_mass()
        fill_label = FILL_MODES[state["fill_mode"]]["label"]
        site = self._first_flight_options(_Step.CHOOSE_SITE)[state["site"]]
        lines = ["🎈 **Balloon Configuration**\n"]
        lines.append(f"Gas: {gas.name}")
        lines.append(f"Fill: {fill_label} → {gas_mass:.3f} kg")
        lines.append(f"Envelope: {envelope.name} — {envelope.max_volume_m3}m³")
        lines.append(f"Payloads: {', '.join(payload_names)}")
        lines.append(f"Site: {site.name}")
        lines.append(
            f"Total mass: {gas_mass + envelope.mass_kg + payload_mass:.1f} kg\n"
        )
        lines.append("Review looks good? Hit **Launch**! 🚀")
        return "\n".join(lines)

    def _step_content(self) -> str:
        from balloon_frontier.discord_ui.configurator import _Step
        from balloon_frontier.story import FIRST_FLIGHT_CHAPTER, story_chapter_intro

        if self._current_step == _Step.REVIEW_LAUNCH:
            configuration = self._build_config_text()
        else:
            player = self._get_player_state()
            options = self._first_flight_options()
            lines = [
                "🔧 **Balloon Configuration**\n",
                f"**Step {self._current_step + 1}/{len(self.STEPS)}:** "
                f"{self.STEP_LABELS[self._current_step]}\n",
            ]
            if self._current_step == _Step.CHOOSE_GAS:
                for index, gas in enumerate(options.values(), 1):
                    lines.append(
                        f"{index}  {gas[0]}  (M={gas[1]} kg/mol, ${gas[2]}/kg)"
                    )
                lines.append(
                    "     Air starts at ambient temperature; heat sources change its density during the simulation."
                )
            elif self._current_step == _Step.CHOOSE_ENVELOPE:
                for index, envelope in enumerate(options.values(), 1):
                    lines.append(f"{index}  {envelope[0]}  ({envelope[1]}m³)")
            elif self._current_step == _Step.CHOOSE_FILL:
                for index, fill in enumerate(options.values(), 1):
                    lines.append(f"{index}  {fill['label']}")
                    lines.append(f"     {fill['description']}")
            elif self._current_step == _Step.CHOOSE_PAYLOADS:
                required = [CATALOG.payload(pid) for pid in FIRST_FLIGHT_REQUIRED_PAYLOADS]
                lines.append("Essential payloads:")
                for payload in required:
                    lines.append(
                        f"•  {payload.name}  ({payload.mass_kg}kg, ${payload.cost})"
                    )
                lines.append("Optional additions:")
                for index, payload in enumerate(options.values(), 1):
                    lines.append(
                        f"{index}  {payload[0]}  ({payload[1]}kg, ${payload[2]})"
                    )
                lines.append(
                    "     Heater choices contribute watts to the same gas energy balance; open-flame methods are flagged in results."
                )
            elif self._current_step == _Step.CHOOSE_SITE:
                for index, site in enumerate(options.values(), 1):
                    lines.append(f"{index}  {site.name}")
                    if site.description:
                        lines.append(f"     {site.description}")
            lines.extend(["", "Click a button to select. Use < Back to go earlier."])
            if player:
                lines.append(
                    f"⚡ You have {player.reputation} reputation and ${player.budget} budget."
                )
            configuration = "\n".join(lines)

        return story_chapter_intro(
            FIRST_FLIGHT_CHAPTER,
            include_disclaimer=False,
        ) + "\n\n" + configuration

    async def _select_single_option(self, interaction, index: int, state_key: str):
        keys = tuple(self._first_flight_options())
        idx = index - 1
        if idx < 0 or idx >= len(keys):
            await interaction.response.send_message(
                "That option isn't available right now.", ephemeral=True
            )
            return
        self.state[state_key] = keys[idx]
        self.state["gas_mass"] = self._compute_gas_mass()
        await self._advance(interaction)

    async def _on_gas(self, interaction, index: int):
        await self._select_single_option(interaction, index, "gas")

    async def _on_envelope(self, interaction, index: int):
        await self._select_single_option(interaction, index, "envelope")

    async def _on_fill(self, interaction, index: int):
        await self._select_single_option(interaction, index, "fill_mode")

    async def _on_payload(self, interaction, index: int):
        keys = tuple(self._first_flight_options())
        idx = index - 1
        if idx < 0 or idx >= len(keys):
            await interaction.response.send_message(
                "That option isn't available right now.", ephemeral=True
            )
            return
        self.state["payloads"] = list(
            toggle_first_flight_optional_payload(
                self.state.get("payloads") or (), keys[idx]
            )
        )
        self.state["gas_mass"] = self._compute_gas_mass()
        self.build_buttons()
        await self._send_step(interaction)

    async def _on_site(self, interaction, index: int):
        await self._select_single_option(interaction, index, "site")

    def build_buttons(self):
        self.state["payloads"] = list(
            with_required_first_flight_payloads(self.state.get("payloads") or ())
        )
        super().build_buttons()

        from balloon_frontier.balloon_cluster import _BalloonCountButton
        from balloon_frontier.discord_ui.configurator import _Step
        from balloon_frontier.discord_ui.modals import _ManualGasMassButton
        from balloon_frontier.discord_ui.views import _OptionButton

        if self._current_step not in FIRST_FLIGHT_OPTION_KEYS:
            return

        self.state["balloon_count"] = 1
        if hasattr(self, "_sync_balloon_count"):
            self._sync_balloon_count()
        for item in list(self.children):
            if isinstance(item, (_OptionButton, _ManualGasMassButton, _BalloonCountButton)):
                self.remove_item(item)

        callback = {
            _Step.CHOOSE_GAS: self._on_gas,
            _Step.CHOOSE_ENVELOPE: self._on_envelope,
            _Step.CHOOSE_FILL: self._on_fill,
            _Step.CHOOSE_PAYLOADS: self._on_payload,
            _Step.CHOOSE_SITE: self._on_site,
        }[self._current_step]
        label = {
            _Step.CHOOSE_GAS: "Choose gas",
            _Step.CHOOSE_ENVELOPE: "Choose envelope",
            _Step.CHOOSE_FILL: "Choose fill",
            _Step.CHOOSE_PAYLOADS: "Toggle optional payload",
            _Step.CHOOSE_SITE: "Choose site",
        }[self._current_step]
        for index in range(1, len(self._first_flight_options()) + 1):
            self.add_item(_OptionButton(index, f"{label} {index}", callback))
