"""First-flight Story onboarding with a deliberately small configuration menu."""

from __future__ import annotations


FIRST_FLIGHT_OPTION_KEYS = {
    0: ("helium", "air"),
    1: ("latex", "candle_kite"),
    2: ("auto", "light", "normal"),
    3: (
        "camera",
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


def _install_first_flight_component_options() -> None:
    """Expose Story-only aerostat components to the legacy tuple menus.

    The canonical definitions are registered in :mod:`balloon_frontier.aerostat`.
    These tuples are presentation adapters used by the existing Discord wizard
    and launch renderer.
    """
    from balloon_frontier.discord_ui.configurator import (
        ENVELOPE_OPTIONS,
        GAS_OPTIONS,
        PAYLOAD_OPTIONS,
    )

    GAS_OPTIONS.setdefault("air", ("Air", 0.0289652068, 0))
    ENVELOPE_OPTIONS.setdefault(
        "candle_kite",
        (
            "Lightweight Hot-Air Envelope",
            0.20,
            0.018,
            1.45,
            1.05,
            5,
        ),
    )
    PAYLOAD_OPTIONS.setdefault(
        "candle_heater",
        ("Tea Light Heat Source", 0.015, 1, False),
    )
    PAYLOAD_OPTIONS.setdefault(
        "electric_heater",
        ("Small Electric Heater", 0.080, 20, False),
    )


class DiscoveryFirstFlightConfiguratorMixin:
    """Expose a small Story menu while using the ordinary simulation physics.

    The first flight changes only which components are offered. Air temperature,
    heater power, envelope heat loss, buoyancy, weather, evaluation, and rewards
    remain on the same shared paths used by later Story flights.
    """

    def _first_flight_options(self, step=None):
        from balloon_frontier.discord_ui.configurator import (
            ENVELOPE_OPTIONS,
            FILL_MODES,
            GAS_OPTIONS,
            PAYLOAD_OPTIONS,
            SITE_OPTIONS,
            _Step,
        )

        _install_first_flight_component_options()
        current_step = self._current_step if step is None else step
        catalogs = {
            _Step.CHOOSE_GAS: GAS_OPTIONS,
            _Step.CHOOSE_ENVELOPE: ENVELOPE_OPTIONS,
            _Step.CHOOSE_FILL: FILL_MODES,
            _Step.CHOOSE_PAYLOADS: PAYLOAD_OPTIONS,
            _Step.CHOOSE_SITE: SITE_OPTIONS,
        }
        catalog = catalogs[current_step]
        return {
            key: catalog[key]
            for key in FIRST_FLIGHT_OPTION_KEYS[current_step]
            if key in catalog
        }

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
                    # GAS_OPTIONS stores molar mass, despite older UI text calling
                    # the value density. Use the physically correct label here.
                    lines.append(
                        f"{index}  {gas[0]}  (M={gas[1]} kg/mol, ${gas[2]}/kg)"
                    )
                lines.append(
                    "     Air starts at ambient temperature; heat sources change its density during the simulation."
                )
            elif self._current_step == _Step.CHOOSE_ENVELOPE:
                for index, envelope in enumerate(options.values(), 1):
                    lines.append(f"{index}  {envelope[0]}  ({envelope[1]}m³)")
                lines.append(
                    "     Envelope heat loss is material-dependent and changes as stretch/inflation changes."
                )
            elif self._current_step == _Step.CHOOSE_FILL:
                for index, fill in enumerate(options.values(), 1):
                    lines.append(f"{index}  {fill['label']}")
                    lines.append(f"     {fill['description']}")
            elif self._current_step == _Step.CHOOSE_PAYLOADS:
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
        key = self._option_by_index(index, self._first_flight_options())
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

    async def _on_fill(self, interaction, index: int):
        await self._select_single_option(interaction, index, "fill_mode")

    async def _on_payload(self, interaction, index: int):
        key = self._option_by_index(index, self._first_flight_options(), multi=True)
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
            _Step.CHOOSE_PAYLOADS: "Toggle payload",
            _Step.CHOOSE_SITE: "Choose site",
        }[self._current_step]
        for index in range(1, len(self._first_flight_options()) + 1):
            self.add_item(_OptionButton(index, f"{label} {index}", callback))
