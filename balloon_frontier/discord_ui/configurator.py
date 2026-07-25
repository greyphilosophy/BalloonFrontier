"""Balloon Frontier — Discord configurator wizard.

Game data (GAS_OPTIONS, ENVELOPE_OPTIONS, etc.) and the step-by-step
interactive walkthrough (BalloonConfigurator + _Step).
"""

import logging
import os
from typing import Optional

import discord

from balloon_frontier.fill import FillMode, apply_fill_mode, calculate_max_safe_gas_mass
from balloon_frontier.launch_sites import LaunchSiteInfo
from balloon_frontier.progression import PlayerRegistry, ENVELOPES as PROGRESSION_ENVELOPES, PAYLOAD_UNLOCKS, SITES, get_envelope
from balloon_frontier.physics import (
    atmosphere_temperature, atmosphere_pressure, atmosphere_density,
    gas_volume, gas_density, buoyant_force, drag_force, spherical_area,
)

from balloon_frontier.discord_ui.views import _OptionButton, _BackButton, _NextButton
from balloon_frontier.discord_ui.modals import _ManualGasMassButton

logger = logging.getLogger(__name__)

# ─── Game Data ────────────────────────────────────────────────────────

GAS_OPTIONS = {
    "helium": ("Helium", 0.0040026, 5),
    "hydrogen": ("Hydrogen", 0.002016, 3),
    "hot_air": ("Hot Air", 0.0289652068, 1),
    "methane": ("Methane", 0.01604, 4),
}

ENVELOPE_OPTIONS = {
    "mylar": ("Mylar Party Balloon", 200.0, 0.05, 2.0, 3.0, 500),
    "latex": ("Latex Weather Balloon", 10.0, 1.0, 3.0, 2.5, 2000),
    "zero_pressure": ("Zero-Pressure Polyethylene", 300.0, 18.0, 1.5, 1.8, 15000),
    "blimp": ("Small Non-Rigid Blimp", 500.0, 45.0, 1.3, 2.0, 50000),
}

PAYLOAD_OPTIONS = {
    "camera": ("Camera", 1.5, 500, False),
    "radio": ("Radio Repeater", 2.0, 800, False),
    "weather_sensor": ("Weather Sensor", 0.8, 1200, False),
    "battery": ("Battery Pack", 3.0, 1000, False),
    "heater": ("Heater", 2.5, 750, False),
    "ballast": ("Ballast (Sand)", 15.0, 300, False),
    "parachute": ("Parachute", 2.0, 600, False),
    "flight_computer": ("Flight Computer", 1.2, 2000, False),
    "valve": ("Pressure Valve", 0.3, 250, True),
    "none": ("None", 1.0, 100, False),
}

SITE_OPTIONS = {
    "field": LaunchSiteInfo(
        name="Open Field",
        altitude_m=0.0,
        temperature_offset_k=0.0,
        wind_strength=2.0,
        description="Flat terrain, mild crosswind",
    ),
    "mountain": LaunchSiteInfo(
        name="Mountain Ridge",
        altitude_m=1500.0,
        temperature_offset_k=-5.0,
        wind_strength=4.0,
        description="Elevated, colder, stronger wind",
    ),
    "rooftop": LaunchSiteInfo(
        name="Urban Rooftop",
        altitude_m=50.0,
        temperature_offset_k=3.0,
        wind_strength=3.0,
        description="Warm microclimate, moderate wind",
    ),
}

FILL_MODES = {
    "auto": {"label": "Auto (Optimal)", "description": "Calculated optimal fill"},
    "light": {"label": "Light", "description": "Less free lift -- slower ascent, higher burst"},
    "normal": {"label": "Normal", "description": "Baseline optimal fill"},
    "heavy": {"label": "Heavy", "description": "More free lift -- faster ascent, earlier burst"},
    "manual": {"label": "Manual", "description": "Your chosen gas mass"},
}

# ─── Step enumeration ─────────────────────────────────────────────────

class _Step:
    CHOOSE_GAS = 0
    CHOOSE_ENVELOPE = 1
    CHOOSE_FILL = 2
    CHOOSE_PAYLOADS = 3
    CHOOSE_SITE = 4
    REVIEW_LAUNCH = 5


# ─── BalloonConfigurator ──────────────────────────────────────────────

class BalloonConfigurator(discord.ui.View):
    """Interactive walkthrough: numbered buttons per step, then review + launch."""

    STEPS = [
        _Step.CHOOSE_GAS,
        _Step.CHOOSE_ENVELOPE,
        _Step.CHOOSE_FILL,
        _Step.CHOOSE_PAYLOADS,
        _Step.CHOOSE_SITE,
        _Step.REVIEW_LAUNCH,
    ]
    STEP_LABELS = [
        "Gas Type",
        "Envelope",
        "Fill Mode",
        "Payloads",
        "Launch Site",
        "Review & Launch",
    ]

    # ── Interaction check ────────────────────────────────────────
    async def _run_checks(self, interaction):
        return True

    # ── Initialization ───────────────────────────────────────────
    def __init__(self):
        super().__init__(timeout=300)
        self.state = {
            "gas": "helium",
            "envelope": "latex",
            "payloads": ["none"],
            "site": "field",
            "fill_mode": "auto",
            "manual_gas_mass": None,
            "gas_mass": None,
        }
        self.state["gas_mass"] = self._compute_gas_mass()
        self._current_step = _Step.CHOOSE_GAS
        self._msg = None
        self._next_btn = None

        # Buttons that persist across all steps.
        self.add_item(_BackButton(self))

        # Build step-specific buttons.
        self.build_buttons()

    # ── Step rendering ────────────────────────────────────────────

    async def _send_step(self, interaction=None):
        """Update the message with the current step."""
        if interaction is not None:
            try:
                await interaction.response.edit_message(
                    content=self._step_content(), view=self,
                )
            except discord.errors.NotFound:
                pass
        else:
            if self._msg is not None:
                try:
                    await self._msg.edit(content=self._step_content(), view=self)
                except discord.errors.NotFound:
                    pass
        # Remember the message for future updates.
        if interaction is not None and interaction.message is not None:
            self._msg = interaction.message

    def _get_player_state(self) -> Optional["PlayerState"]:
        """Look up the current Discord user's player state."""
        if hasattr(self, "_msg") and self._msg is not None:
            try:
                user_id = self._msg.author.id if self._msg.author else None
            except Exception:
                user_id = None
        else:
            user_id = None
        if user_id is None:
            user_id = "anonymous"
        return PlayerRegistry.get_or_create(str(user_id))

    def _is_item_unlocked(self, item_key: str) -> bool:
        """Discord configuration shows all items regardless of progression.

        Progression unlocks gate mission eligibility and the in-game shop,
        not the configuration UI itself. Players can experiment with any
        balloon type.
        """
        return True

    def _step_content(self) -> str:
        step = self._current_step
        if step == _Step.REVIEW_LAUNCH:
            return self._build_config_text()

        label = self.STEP_LABELS[step]
        lines = [
            f"\U0001f527 **Balloon Configuration**\n",
            f"**Step {step + 1}/{len(self.STEPS)}:** {label}\n",
        ]

        # Pull progression data so we can mark locked items
        player = self._get_player_state()

        if step == _Step.CHOOSE_GAS:
            for i, (k, v) in enumerate(GAS_OPTIONS.items(), 1):
                lines.append(f"{i}  {v[0]}  (\u03c1={v[1]} kg/m\u00b3, ${v[2]}/kg)")
        elif step == _Step.CHOOSE_ENVELOPE:
            prog_env_lookup = {e.id: e for e in PROGRESSION_ENVELOPES}
            for i, (key, v) in enumerate(ENVELOPE_OPTIONS.items(), 1):
                prog_env = prog_env_lookup.get(key)
                unlocked = player.is_envelope_unlocked(key) if player else key == "latex"
                if unlocked:
                    lines.append(f"{i}  {v[0]}  ({v[1]}m\u00b3)")
                else:
                    needs = ""
                    if prog_env and (prog_env.cost > 0 or prog_env.min_reputation > 0):
                        if prog_env.cost > 0 and prog_env.min_reputation > 0:
                            needs = f" \U0001f512 Needs {prog_env.cost} credits OR {prog_env.min_reputation} rep"
                        elif prog_env.cost > 0:
                            needs = f" \U0001f512 Needs {prog_env.cost} credits"
                        else:
                            needs = f" \U0001f512 Needs {prog_env.min_reputation} reputation"
                    else:
                        needs = " (unlocked!) \U0001f513"
                    lines.append(f"{i}  {v[0]}  ({v[1]}m\u00b3){needs}")
        elif step == _Step.CHOOSE_FILL:
            for i, (k, info) in enumerate(FILL_MODES.items(), 1):
                lines.append(f"{i}  {info['label']}")
                lines.append(f"     {info['description']}")
        elif step == _Step.CHOOSE_PAYLOADS:
            prog_payload_lookup = {p.id: p for p in PAYLOAD_UNLOCKS}
            for i, (key, v) in enumerate(PAYLOAD_OPTIONS.items(), 1):
                prog_payload = prog_payload_lookup.get(key)
                unlocked = True
                lock_note = ""
                if prog_payload is not None:
                    unlocked = player.is_payload_unlocked(key) if player else True
                    if not unlocked:
                        lock_note = f" \U0001f512 ({prog_payload.min_reputation}rep/{prog_payload.cost}cr)"
                lines.append(f"{i}  {v[0]}  ({v[1]}kg, ${v[2]}){lock_note}")
        elif step == _Step.CHOOSE_SITE:
            prog_site_lookup = {s.id: s for s in SITES}
            for i, (key, v) in enumerate(SITE_OPTIONS.items(), 1):
                prog_site = prog_site_lookup.get(key)
                unlocked = True
                lock_note = ""
                if prog_site is not None:
                    unlocked = player.is_site_unlocked(key) if player else True
                    if not unlocked:
                        lock_note = f" \U0001f512 (Needs {prog_site.min_reputation}rep / {prog_site.cost}cr)"
                lines.append(f"{i}  {v.name}")
                if v.description:
                    lines.append(f"     {v.description}")
                if lock_note:
                    lines.append(lock_note)

        lines.append("")
        cur = self.state
        if step < _Step.REVIEW_LAUNCH:
            lines.append(
                "Click a button to select. Use < Back to go earlier."
            )
        if player:
            lines.append(f"\u26a1 You have {player.reputation} reputation and ${player.budget} budget.")
        return "\n".join(lines)

    # ── Step navigation ───────────────────────────────────────────

    async def _advance(self, interaction):
        """Advance to the next step, rebuild buttons, then update the message."""
        self._current_step += 1
        if self._current_step > _Step.REVIEW_LAUNCH:
            self._current_step = _Step.REVIEW_LAUNCH
        # Build buttons BEFORE editing the message to avoid stale controls
        self.build_buttons()
        await self._send_step(interaction)

    # ── Back button ───────────────────────────────────────────────

    def _prev_step(self):
        if self._current_step > _Step.CHOOSE_GAS:
            self._current_step -= 1
            return True
        return False

    # ── Option helpers ────────────────────────────────────────────

    def _option_by_index(self, index: int, options: dict, multi: bool = False):
        """Resolve a 1-based button index \u2192 option key(s)."""
        keys = list(options.keys())
        idx = index - 1
        if idx < 0 or idx >= len(keys):
            return None
        if multi:
            selected = keys[idx]
            current = set(self.state["payloads"])
            if selected in current:
                current.discard(selected)
                if not current:
                    current = {"none"}
            elif selected == "none":
                current = {"none"}
            else:
                current.discard("none")
                current.add(selected)
            self.state["payloads"] = list(current)
            return list(current)
        return keys[idx]

    def _option_by_index_filtered(
        self, index: int, options: dict, multi: bool = False
    ) -> Optional[list]:
        """Resolve a 1-based button index \u2192 option key(s), filtering out locked items first."""
        keys = [k for k in options.keys() if self._is_item_unlocked(k)]
        idx = index - 1
        if idx < 0 or idx >= len(keys):
            return None
        if multi:
            selected = keys[idx]
            current = set(self.state["payloads"])
            if selected in current:
                current.discard(selected)
                if not current:
                    current = {"none"}
            elif selected == "none":
                current = {"none"}
            else:
                current.discard("none")
                current.add(selected)
            self.state["payloads"] = list(current)
            return list(current)
        return keys[idx]

    # ── Button callbacks ──────────────────────────────────────────

    async def _on_gas(self, interaction, index: int):
        key = self._option_by_index(index, GAS_OPTIONS) or "gas"
        self.state["gas"] = key
        self.state["gas_mass"] = self._compute_gas_mass()
        await self._advance(interaction)

    async def _on_envelope(self, interaction, index: int):
        key = self._option_by_index(index, ENVELOPE_OPTIONS)
        if key is None:
            key = "envelope"
        # Block locked envelopes
        player = self._get_player_state()
        if not player.is_envelope_unlocked(key):  # type: ignore[arg-type]
            prog_env = get_envelope(key)
            await interaction.response.send_message(
                f"\U0001f512 **{prog_env.name}** is locked!\n"
                f"Unlock by reaching {prog_env.min_reputation} reputation OR {prog_env.cost} credits.",
                ephemeral=True,
            )
            return
        self.state["envelope"] = key
        self.state["gas_mass"] = self._compute_gas_mass()
        await self._advance(interaction)

    async def _on_fill(self, interaction, index: int):
        key = self._option_by_index(index, FILL_MODES) or "fill_mode"
        self.state["fill_mode"] = key
        self.state["gas_mass"] = self._compute_gas_mass()
        await self._advance(interaction)

    async def _on_payload(self, interaction, index: int):
        filtered = [k for k in PAYLOAD_OPTIONS.keys() if self._is_item_unlocked(k)]
        key = self._option_by_index_filtered(index, PAYLOAD_OPTIONS, multi=True)
        if key is None or (isinstance(key, list) and len(key) == 0):
            await interaction.response.send_message(
                "That option isn't available right now.",
                ephemeral=True,
            )
            return
        self.state["gas_mass"] = self._compute_gas_mass()
        # Rebuild buttons and edit message (no auto-advance for payloads)
        self.build_buttons()
        await self._send_step(interaction)

    async def _on_site(self, interaction, index: int):
        filtered_keys = [k for k in SITE_OPTIONS.keys() if self._is_item_unlocked(k)]
        idx = index - 1
        if idx < 0 or idx >= len(filtered_keys):
            await interaction.response.send_message(
                "That option isn't available right now.",
                ephemeral=True,
            )
            return
        key = filtered_keys[idx]
        self.state["site"] = key
        self.state["gas_mass"] = self._compute_gas_mass()
        await self._advance(interaction)

    async def _on_back(self, interaction):
        if self._prev_step():
            self.build_buttons()
            await self._send_step(interaction)

    # ── Build buttons for current step ────────────────────────────

    def build_buttons(self):
        """Clear existing buttons (except Back) and add step buttons + Launch."""
        new_items = [item for item in self.children if isinstance(item, _BackButton)]
        self.clear_items()
        for item in new_items:
            self.add_item(item)

        if self._current_step == _Step.CHOOSE_GAS:
            for i in range(1, len(GAS_OPTIONS) + 1):
                self.add_item(_OptionButton(i, f"Choose gas {i}", self._on_gas))
        elif self._current_step == _Step.CHOOSE_ENVELOPE:
            for i, key in enumerate([k for k in ENVELOPE_OPTIONS if self._is_item_unlocked(k)], 1):
                self.add_item(_OptionButton(i, f"Choose envelope {i}", self._on_envelope))
        elif self._current_step == _Step.CHOOSE_FILL:
            for i in range(1, len(FILL_MODES) + 1):
                self.add_item(_OptionButton(i, f"Choose fill {i}", self._on_fill))
            self.add_item(_ManualGasMassButton(self))
        elif self._current_step == _Step.CHOOSE_PAYLOADS:
            for i, key in enumerate([k for k in PAYLOAD_OPTIONS if self._is_item_unlocked(k)], 1):
                self.add_item(_OptionButton(i, f"Toggle payload {i}", self._on_payload))
            self.add_item(_NextButton(self))
        elif self._current_step == _Step.CHOOSE_SITE:
            for i, key in enumerate([k for k in SITE_OPTIONS if self._is_item_unlocked(k)], 1):
                self.add_item(_OptionButton(i, f"Choose site {i}", self._on_site))
        elif self._current_step == _Step.REVIEW_LAUNCH:
            from balloon_frontier.discord_ui.modals import _LaunchButton
            self.add_item(_LaunchButton(self))

    # ── Gas mass helpers ──────────────────────────────────────────

    def _get_site_conditions(self):
        """Derive launch conditions (altitude, pressure, temperature) from the selected site."""
        site = SITE_OPTIONS[self.state["site"]]
        return site.derive_conditions()

    def _get_env_params(self):
        """Build envelope + site params to pass to shared fill functions."""
        env_id = self.state["envelope"]
        site_cond = self._get_site_conditions()
        return {
            "envelope_type": env_id,
            "launch_altitude": site_cond.get("launch_altitude"),
            "launch_pressure": site_cond.get("launch_pressure"),
            "gas_temperature": site_cond.get("gas_temperature"),
        }

    def _compute_gas_mass(self):
        """Compute gas mass based on current fill_mode, envelope, and gas."""
        gas_type = self.state["gas"]
        env_id = self.state["envelope"]
        fill_mode = self.state["fill_mode"]
        env_info = ENVELOPE_OPTIONS[env_id]
        volume = env_info[1]
        env_params = self._get_env_params()
        mode_map = {
            "auto": FillMode.AUTO,
            "light": FillMode.LIGHT,
            "normal": FillMode.NORMAL,
            "heavy": FillMode.HEAVY,
            "manual": FillMode.MANUAL,
        }
        mode = mode_map.get(fill_mode, FillMode.AUTO)
        if mode == FillMode.MANUAL:
            manual_mass = self.state.get("manual_gas_mass")
            if manual_mass is None:
                manual_mass = calculate_max_safe_gas_mass(
                    volume, gas_type, **env_params
                )
                self.state["manual_gas_mass"] = manual_mass
            mass = apply_fill_mode(
                volume, gas_type, FillMode.MANUAL,
                manual_mass_kg=manual_mass, **env_params
            )
        else:
            mass = apply_fill_mode(
                volume, gas_type, mode, **env_params
            )
        return round(mass, 3)

    def _build_config_text(self):
        """Build a text summary of current config."""
        s = self.state
        gas = GAS_OPTIONS[s["gas"]]
        env = ENVELOPE_OPTIONS[s["envelope"]]
        site = SITE_OPTIONS[s["site"]]
        payloads = [PAYLOAD_OPTIONS[p] for p in s["payloads"]]
        payload_names = [p[0] for p in payloads]
        payload_mass = sum(p[1] for p in payloads)
        gas_mass = self.state.get("gas_mass")
        if gas_mass is None:
            gas_mass = self._compute_gas_mass()
            self.state["gas_mass"] = gas_mass
        fill_label = FILL_MODES[s["fill_mode"]]["label"]
        lines = [f"\U0001f388 **Balloon Configuration**\n"]
        lines.append(f"Gas: {gas[0]}")
        lines.append(f"Fill: {fill_label} \u2192 {gas_mass:.3f} kg")
        lines.append(f"Envelope: {env[0]} \u2014 {env[1]}m\u00b3")
        lines.append(f"Payloads: {', '.join(payload_names)}")
        lines.append(f"Site: {site.name}")
        lines.append(f"Total mass: {gas_mass + env[2] + payload_mass:.1f} kg\n")
        lines.append("Review looks good? Hit **Launch**! \U0001f680")
        return "\n".join(lines)
