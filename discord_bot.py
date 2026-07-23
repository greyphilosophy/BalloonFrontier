"""Balloon Frontier — Discord Bot

Interactive select-menu UI for the balloon simulation game.
Uses the Python physics engine (`balloon_frontier/physics.py`).
"""

import asyncio
import logging
import os
import traceback

import discord
from discord.ext import commands

from balloon_frontier.physics import (
    atmosphere_temperature, atmosphere_pressure, atmosphere_density,
    gas_volume, gas_density, buoyant_force, drag_force, spherical_area,
)
from balloon_frontier.fill import (
    apply_fill_mode,
    calculate_max_safe_gas_mass,
    FillMode,
)
from balloon_frontier.simulation import run_simulation as run_full_simulation
from balloon_frontier.ascii_chart import chart_to_string
from balloon_frontier.mission_selection import (
    assign_missions_to_flight,
    seed_from_game_state,
    choose_mission_count,
)
from balloon_frontier.flight_score import calculate_flight_score
from balloon_frontier.medal_tier import get_medal_tier, get_medal_emoji, medal_tier_to_string
from balloon_frontier.launch_sites import LaunchSiteInfo
from balloon_frontier.narrative_result import format_discord_results
from balloon_frontier.weather_event import generate_weather, weather_impact_on_flight, format_weather_briefing
from balloon_frontier.missions import load_mission_directory

logger = logging.getLogger("balloon_frontier_bot")

# ─── Game Data ────────────────────────────────────────────────────────

GAS_OPTIONS = {
    "helium": ("Helium", 0.0040026, 5),
    "hydrogen": ("Hydrogen", 0.002016, 3),
    "hot_air": ("Hot Air", 0.0289652068, 1),
    "methane": ("Methane", 0.01604, 4),
}

ENVELOPE_OPTIONS = {
    # Tuple layout used by the Discord simulation:
    # (display_name, envelope_vol_m3, <unused>, drag_coeff, burst_stretch_ratio, <unused>)
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
    "valve": ("Pressure Valve", 0.3, 250, True),  # Prevents bursting by venting gas
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

# ─── Fill mode presets ────────────────────────────────────────────────

FILL_MODES = {
    "auto": {"label": "Auto (Optimal)", "description": "Calculated optimal fill"},
    "light": {"label": "Light", "description": "Less free lift — slower ascent, higher burst"},
    "normal": {"label": "Normal", "description": "Baseline optimal fill"},
    "heavy": {"label": "Heavy", "description": "More free lift — faster ascent, earlier burst"},
    "manual": {"label": "Manual", "description": "Your chosen gas mass"},
}


# ─── Simulation ────────────────────────────────────────────────────────

# Lazily load missions so they're available for evaluation.
_missions_loaded = False

def _ensure_missions_loaded():
    global _missions_loaded
    if not _missions_loaded:
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            mission_dir = os.path.join(here, "data", "missions")
            load_mission_directory(mission_dir)
        except Exception:
            pass
        _missions_loaded = True


def run_simulation(
    gas_type,
    gas_mass,
    gas_temperature_k,
    payload_mass,
    drag_coeff,
    envelope_vol,
    stretch_ratio,
    *,
    mission_assignment=None,
    env_config=None,
    weather_impacts=None,
    has_pressure_valve=False,  # Valve prevents burst by venting gas
):
    """Run fixed-step vertical simulation using the full physics engine.

    This function replaces the hand-rolled simplified simulation with the
    proper simulation engine from balloon_frontier.simulation, which includes
    thermal model, wind drift, permeability leak, and burst detection.

    The API signature is preserved so existing callers (and tests) work
    without modification.

    Args:
        env_config: Optional EnvelopeConfig to use instead of building one.
        weather_impacts: Optional dict with weather modifiers (burst_risk,
            thermal_efficiency, pressure_modifier).

    Returns:
        (telemetry, summary) where:
            telemetry: list of step dicts (with 'time' and 'alt' keys for
                       backward compat with Discord result rendering)
            summary: dict with peak_altitude, burst, time_of_flight, etc.
    """
    _ensure_missions_loaded()

    from balloon_frontier.simulation import SimulationState, EnvelopeConfig

    # Build the envelope config from the Discord API parameters.
    if env_config is None:
        env_config = EnvelopeConfig(
            max_volume_m3=envelope_vol,
            burst_stretch_ratio=stretch_ratio,
            drag_coefficient=drag_coeff,
            mass_kg=1.0,  # default envelope mass for Discord mode
            contained_gas=True,
        )

    # Apply weather modifiers to the envelope config and simulation state.
    # All values are dimensionless multipliers (centered on 1.0 = normal).
    if weather_impacts:
        env_config.weather_burst_risk_modifier = weather_impacts.get("burst_risk", 1.0)
        env_config.weather_solar_modifier = weather_impacts.get("thermal_efficiency", 1.0)
        env_config.weather_pressure_modifier = weather_impacts.get("pressure_modifier", 1.0)
        # ascent_rate: thermal/buoyancy multiplier (~1.0 normal, >1.0 hot/updraft, <1.0 cold/downdraft)
        env_config.weather_ascent_multiplier = weather_impacts.get("ascent_rate", 1.0)
        # drift_factor: horizontal wind scaling (~1.0 normal)
        env_config.weather_drift_multiplier = weather_impacts.get("drift_factor", 1.0)

    state = SimulationState(
        gas_type=gas_type,
        gas_mass_kg=gas_mass,
        payload_mass_kg=payload_mass,
        envelope=env_config,
        altitude_m=0.0,
        gas_temperature_k=gas_temperature_k,
        weather_ascent_multiplier=env_config.weather_ascent_multiplier if weather_impacts else 1.0,
        weather_drift_multiplier=env_config.weather_drift_multiplier if weather_impacts else 1.0,
        wind_enabled=True,
        wind_site_id="field",
        ballast_mass_kg=0.0,  # User controls mass entirely via payloads — no hidden ballast
        has_pressure_valve=has_pressure_valve,  # Valve prevents burst by venting gas
    )

    # Run with the full physics engine. Time limit depends on whether missions are active.
    # For mission launches we may need up to 12 hours (43200s) of flight time.
    # We set step_interval=1.0 to store only 1 sample per second, avoiding 432k ticks
    # in memory. Physics still runs at dt=0.1 internally — we just skip storing intermediate
    # steps, so we don't need post-hoc downsampling or peak-memory spikes.
    if mission_assignment:
        max_time = 43200.0  # 12 hours default for mission launches
        max_steps = int(max_time / 0.1)
        tel_full = run_full_simulation(
            state, dt=0.1, total_time_s=max_time, max_steps=max_steps,
            step_interval=1.0,  # Store 1 sample per second only (~43k vs 432k)
        )
    else:
        tel_full = run_full_simulation(state, dt=0.1, total_time_s=150.0, max_steps=10000)

    if not tel_full:
        return [], {
            "peak_altitude": 0,
            "burst": False,
            "time_of_flight": 0,
            "payload_count": 1,
            "score": 0,
            "medal": medal_tier_to_string(0),
            "medal_emoji": "⚪",
        }

    # Extract peak altitude and burst from the full telemetry.
    peak_alt = max(t["altitude_m"] for t in tel_full)
    burst = any(t.get("burst", False) for t in tel_full)
    landed = any(t.get("landed", False) for t in tel_full)
    crashed = any(t.get("crashed", False) for t in tel_full)

    # Convert full telemetry to the simpler format expected by Discord.
    # Keep every step for the chart, but the original code only sampled
    # every 4000 steps (at dt=0.5).  We sample similarly for compat.
    telemetry = []
    step_idx = 0
    for t in tel_full:
        telemetry.append({
            "time": t["time_s"],
            "alt": t["altitude_m"],
            "vel": t["velocity_mps"],
            "burst": t.get("burst", False),
            "landed": t.get("landed", False),
            "crashed": t.get("crashed", False),
        })
        step_idx += 1

    flight_time = tel_full[-1]["time_s"]

    # Payload count: count actual payloads (at least 1 for scoring).
    payload_count = 1

    score = calculate_flight_score(peak_alt, payload_count, flight_time)
    medal_name = medal_tier_to_string(peak_alt)
    medal_emoji = get_medal_emoji(peak_alt)

    summary = {
        "peak_altitude": peak_alt,
        "burst": burst,
        "landed": landed,
        "crashed": crashed,
        "time_of_flight": flight_time,
        "payload_count": payload_count,
        "score": score,
        "medal": medal_name,
        "medal_emoji": medal_emoji,
    }

    if mission_assignment:
        summary["assigned_missions"] = list(mission_assignment.get("missions", []))
        summary["mission_seed"] = mission_assignment.get("seed")
        summary["mission_count"] = mission_assignment.get("mission_count")

    return telemetry, summary


def format_score_breakdown(score, peak_alt, payload_count, time_of_flight):
    """Format the score breakdown string."""
    alt_pts = int(peak_alt * 1.0)
    pay_pts = int(payload_count * 500.0)
    time_pts = int(time_of_flight * 100.0)
    lines = []
    lines.append(f"  Altitude: {alt_pts:,} pts")
    lines.append(f"  Payloads: {pay_pts:,} pts")
    lines.append(f"  Time: {time_pts:,} pts")
    lines.append(f"  ─────────────────")
    lines.append(f"  TOTAL: {int(score):,} pts")
    return "\n".join(lines)


def make_result_embed(gas_name, gas_mass, env_name, payload_name, site_name,
                      telemetry, summary):
    """Build result embed for a launch."""
    # Be defensive: results rendering should not crash if summary is missing
    # optional fields.
    peak = summary.get("peak_altitude", 0)
    burst = summary.get("burst", False)
    time_of_flight = summary.get("time_of_flight", 0)
    payload_count = summary.get("payload_count", 1)
    score = summary.get(
        "score",
        calculate_flight_score(peak, payload_count, time_of_flight),
    )

    medal_name = summary.get("medal", medal_tier_to_string(peak))
    medal_emoji = summary.get("medal_emoji", get_medal_emoji(peak))

    target = 30000
    status = "🟢" if peak >= target else "🟡" if peak >= target * 0.7 else "🔵"

    lines = ["🎈 **Launch Report**\n"]
    lines.append(f"Gas: {gas_name} | Mass: {gas_mass}kg")
    lines.append(f"Envelope: {env_name}")
    lines.append(f"Site: {site_name}\n")

    missions = summary.get("assigned_missions")
    if missions:
        lines.append(f"Missions: {', '.join(missions)}\n")

    lines.append(f"Altitude: {status} {peak:,.0f}m / {target:,}m target")
    lines.append(f"Time of Flight: {time_of_flight:.1f}s")
    lines.append(f"Burst: {'💥 Yes' if burst else '🟢 No'}")
    lines.append(f"Medal: {medal_emoji} **{medal_name}**")
    lines.append("")

    # Score section
    lines.append("🏆 **Score Breakdown**")
    lines.append(format_score_breakdown(score, peak, payload_count, time_of_flight))
    lines.append("")

    # Generate ASCII trajectory chart
    time_arr = [r["time"] for r in telemetry]
    alt_arr = [r["alt"] for r in telemetry]
    chart = chart_to_string(
        time_arr, alt_arr,
        title="📈 Flight Trajectory"
    )

    lines.append(chart + "\n")
    # Telemetry
    sampled = telemetry[::1]
    for r in sampled[:15]:
        v_dir = "↑" if r["vel"] > 0 else "↓"
        lines.append(f"⏱ {r['time']:.0f}s  {r['alt']:>8,.0f}m  {v_dir}")

    content = "\n".join(lines)
    return content


# ─── Bot ──────────────────────────────────────────────────────────────

intents = discord.Intents(message_content=True, guilds=True)
bot = commands.Bot(command_prefix="/", intents=intents)
bot.remove_command("help")


@bot.event
async def on_ready():
    logger.info(f"Balloon Frontier online as {bot.user} ({bot.user.id})")


@bot.event
async def on_message(message):
    """Process messages so prefix commands (/help, /physics, /launch) fire."""
    await bot.process_commands(message)


# ─── Configurator — step-by-step interactive walkthrough ──────────

# Step enumeration (used in button styles)
class _Step:
    CHOOSE_GAS = 0
    CHOOSE_ENVELOPE = 1
    CHOOSE_FILL = 2
    CHOOSE_PAYLOADS = 3
    CHOOSE_SITE = 4
    REVIEW_LAUNCH = 5


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

    def _step_content(self) -> str:
        step = self._current_step
        if step == _Step.REVIEW_LAUNCH:
            return self._build_config_text()

        label = self.STEP_LABELS[step]
        lines = [
            f"🔧 **Balloon Configuration**\n",
            f"**Step {step + 1}/{len(self.STEPS)}:** {label}\n",
        ]

        if step == _Step.CHOOSE_GAS:
            for i, (k, v) in enumerate(GAS_OPTIONS.items(), 1):
                lines.append(f"{i}  {v[0]}  (ρ={v[1]} kg/m³, ${v[2]}/kg)")
        elif step == _Step.CHOOSE_ENVELOPE:
            for i, (k, v) in enumerate(ENVELOPE_OPTIONS.items(), 1):
                lines.append(f"{i}  {v[0]}  ({v[1]}m³)")
        elif step == _Step.CHOOSE_FILL:
            for i, (k, info) in enumerate(FILL_MODES.items(), 1):
                lines.append(f"{i}  {info['label']}")
                lines.append(f"     {info['description']}")
        elif step == _Step.CHOOSE_PAYLOADS:
            for i, (k, v) in enumerate(PAYLOAD_OPTIONS.items(), 1):
                lines.append(f"{i}  {v[0]}  ({v[1]}kg, ${v[2]})")
        elif step == _Step.CHOOSE_SITE:
            for i, (_, v) in enumerate(SITE_OPTIONS.items(), 1):
                lines.append(f"{i}  {v.name}")
                lines.append(f"     {v.description}")

        lines.append("")
        cur = self.state
        if step < _Step.REVIEW_LAUNCH:
            lines.append(
                "Click a button to select. Use < Back to go earlier."
            )
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
        """Resolve a 1-based button index → option key(s)."""
        keys = list(options.keys())
        idx = index - 1
        if idx < 0 or idx >= len(keys):
            return None
        if multi:
            selected = keys[idx]
            current = set(self.state["payloads"])
            if selected in current:
                # Deselect: remove it; if nothing left, reset to sentinel
                current.discard(selected)
                if not current:
                    current = {"none"}
            elif selected == "none":
                # "none" selected after real payloads → clear to just {"none"}
                current = {"none"}
            else:
                # Real payload selected → remove sentinel, add real one
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
        key = self._option_by_index(index, ENVELOPE_OPTIONS) or "envelope"
        self.state["envelope"] = key
        self.state["gas_mass"] = self._compute_gas_mass()
        await self._advance(interaction)

    async def _on_fill(self, interaction, index: int):
        key = self._option_by_index(index, FILL_MODES) or "fill_mode"
        self.state["fill_mode"] = key
        self.state["gas_mass"] = self._compute_gas_mass()
        await self._advance(interaction)

    async def _on_payload(self, interaction, index: int):
        self._option_by_index(index, PAYLOAD_OPTIONS, multi=True)
        self.state["gas_mass"] = self._compute_gas_mass()
        # Rebuild buttons and edit message (no auto-advance for payloads)
        self.build_buttons()
        await self._send_step(interaction)

    async def _on_site(self, interaction, index: int):
        key = self._option_by_index(index, SITE_OPTIONS) or "site"
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
        # Remove all buttons
        new_items = [item for item in self.children if isinstance(item, _BackButton)]
        self.clear_items()
        for item in new_items:
            self.add_item(item)

        if self._current_step == _Step.CHOOSE_GAS:
            for i in range(1, len(GAS_OPTIONS) + 1):
                self.add_item(_OptionButton(i, f"Choose gas {i}", self._on_gas))
        elif self._current_step == _Step.CHOOSE_ENVELOPE:
            for i in range(1, len(ENVELOPE_OPTIONS) + 1):
                self.add_item(_OptionButton(i, f"Choose envelope {i}", self._on_envelope))
        elif self._current_step == _Step.CHOOSE_FILL:
            for i in range(1, len(FILL_MODES) + 1):
                self.add_item(_OptionButton(i, f"Choose fill {i}", self._on_fill))
            self.add_item(_ManualGasMassButton(self))
        elif self._current_step == _Step.CHOOSE_PAYLOADS:
            for i in range(1, len(PAYLOAD_OPTIONS) + 1):
                self.add_item(_OptionButton(i, f"Toggle payload {i}", self._on_payload))
            self.add_item(_LaunchButton(self))
        elif self._current_step == _Step.CHOOSE_SITE:
            for i in range(1, len(SITE_OPTIONS) + 1):
                self.add_item(_OptionButton(i, f"Choose site {i}", self._on_site))
            self.add_item(_LaunchButton(self))
        elif self._current_step == _Step.REVIEW_LAUNCH:
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
        lines = [f"🎈 **Balloon Configuration**\n"]
        lines.append(f"Gas: {gas[0]}")
        lines.append(f"Fill: {fill_label} → {gas_mass:.3f} kg")
        lines.append(f"Envelope: {env[0]} — {env[1]}m³")
        lines.append(f"Payloads: {', '.join(payload_names)}")
        lines.append(f"Site: {site.name}")
        lines.append(f"Total mass: {gas_mass + env[2] + payload_mass:.1f} kg\n")
        lines.append("Review looks good? Hit **Launch**! 🚀")
        return "\n".join(lines)


# ─── Button classes for the walkthrough ──────────────────────────

class _OptionButton(discord.ui.Button):
    """A numbered option button. Callback is a function on the bot client."""
    def __init__(self, index: int, style_label: str, callback_factory):
        super().__init__(
            label=style_label,
            style=discord.ButtonStyle.primary,
            custom_id=f"cfg_option_{index}",
        )
        self._index = index
        self._callback = callback_factory

    async def callback(self, interaction: discord.Interaction):
        await self._callback(interaction, self._index)


class _BackButton(discord.ui.Button):
    """Back button present on every step except the first."""
    def __init__(self, parent: BalloonConfigurator):
        super().__init__(
            label="◀ Back",
            style=discord.ButtonStyle.secondary,
            custom_id="cfg_back",
        )
        self._parent = parent

    async def callback(self, interaction: discord.Interaction):
        await self._parent._on_back(interaction)


class _ManualGasMassButton(discord.ui.Button):
    """Button that opens the manual gas mass modal."""
    def __init__(self, parent: "BalloonConfigurator"):
        super().__init__(
            label="Edit Gas Mass",
            style=discord.ButtonStyle.secondary,
            custom_id="cfg_manual_mass",
        )
        self._parent = parent

    async def callback(self, interaction: discord.Interaction):
        modal = _ManualGasMassModal(self._parent)
        await interaction.response.send_modal(modal)


class _ManualGasMassModal(discord.ui.Modal):
    """Modal to set the manual gas mass (kg)."""

    def __init__(self, parent: "BalloonConfigurator"):
        super().__init__(title="Manual Gas Mass")
        self._parent = parent

        current = parent.state.get("manual_gas_mass")
        default_str = "" if current is None else str(current)

        self.mass_input = discord.ui.TextInput(
            label="Gas mass (kg)",
            placeholder="e.g. 12.5",
            default=default_str,
            required=True,
            max_length=20,
        )
        self.add_item(self.mass_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = float(str(self.mass_input.value).strip())
        except Exception:
            await interaction.response.send_message(
                "❌ Please enter a valid number for gas mass.",
                ephemeral=True,
            )
            return

        val = max(0.001, val)
        self._parent.state["manual_gas_mass"] = val
        if self._parent.state.get("fill_mode") == "manual":
            self._parent.state["gas_mass"] = self._parent._compute_gas_mass()

        if getattr(self._parent, "_msg", None) is not None:
            await self._parent._msg.edit(
                content=self._parent._step_content(), view=self._parent,
            )

        await interaction.response.send_message(
            "✅ Manual gas mass updated.",
            ephemeral=True,
        )


class _LaunchButton(discord.ui.Button):
    def __init__(self, parent, label="🚀 Launch", callback=None):
        super().__init__(label=label, style=discord.ButtonStyle.success)
        self._parent = parent

    async def callback(self, interaction):
        # Defer immediately so the event loop isn't blocked by CPU work.
        await interaction.response.defer(thinking=True, ephemeral=False)

        state = self._parent.state
        gas_info = GAS_OPTIONS[state["gas"]]
        env_info = ENVELOPE_OPTIONS[state["envelope"]]
        site_info = SITE_OPTIONS[state["site"]]
        payloads = [PAYLOAD_OPTIONS[p] for p in state["payloads"]]
        payload_names = [p[0] for p in payloads]
        payload_mass = sum(p[1] for p in payloads)
        has_pressure_valve = any(p[3] for p in payloads)  # 4th element = has valve

        # Use cached gas mass from the configurator state.
        gas_mass = self._parent.state.get("gas_mass")
        if gas_mass is None:
            gas_mass = self._parent._compute_gas_mass()
            self._parent.state["gas_mass"] = gas_mass

        try:
            payload_keys = list(state.get("payloads") or [])
            payload_count = len(payload_keys) if payload_keys else 0
            mission_count = choose_mission_count(payload_count)

            mission_seed = seed_from_game_state(
                gas=state["gas"],
                envelope=state["envelope"],
                payloads=payload_keys,
                site=state["site"],
            )
            mission_assignment = assign_missions_to_flight(
                payload_count=payload_count,
                seed=mission_seed,
                mission_count=mission_count,
            )

            site_cond = self._parent._get_site_conditions()

            # Generate weather based on launch configuration
            weather = generate_weather(
                site=state["site"],
                gas=state["gas"],
                envelope=state["envelope"],
                payloads=payload_keys,
                seed=mission_seed,
            )
            weather_dict = {
                "name": weather.name,
                "description": weather.description,
                "severity": weather.severity,
                "flight_modifier": weather.flight_modifier,
            }

            # Compute weather impacts and pass them to the simulation
            weather_impacts = weather_impact_on_flight(weather)

            # Run the CPU-heavy simulation off the event loop.
            tel, summary = await asyncio.to_thread(
                run_simulation,
                state["gas"], gas_mass, site_cond["gas_temperature"], payload_mass,
                env_info[3], env_info[1], env_info[4],
                mission_assignment=mission_assignment,
                weather_impacts=weather_impacts,
                has_pressure_valve=has_pressure_valve,
            )

            payload_display = ", ".join(payload_names)
            if payload_keys and "none" not in payload_keys:
                pass  # keep as is
            elif payload_keys == ["none"]:
                payload_display = "None"

            # Generate chart from telemetry
            time_arr = [r["time"] for r in tel]
            alt_arr = [r["alt"] for r in tel]
            chart = chart_to_string(
                time_arr, alt_arr,
                title="📈 Flight Trajectory"
            )

            # Get player ID from the interaction for progression tracking
            player_id = str(interaction.user.id) if hasattr(interaction, 'user') and interaction.user else "anonymous"

            # Build narrative result
            result_content = format_discord_results(
                peak_altitude=summary.get("peak_altitude", 0),
                burst=summary.get("burst", False),
                landed=summary.get("landed", False),
                crashed=summary.get("crashed", False),
                time_of_flight=summary.get("time_of_flight", 0),
                telemetry=tel,
                gas_name=gas_info[0],
                gas_mass=gas_mass,
                env_name=env_info[0],
                payload_names=payload_display,
                site_name=site_info.name,
                mission_assignment=mission_assignment,
                player_id=player_id,
                weather_event=weather_dict,
                chart_str=chart,
            )

            # Truncate if too long
            if len(result_content) > 2000:
                result_content = result_content[:1997] + "..."
            await interaction.edit_original_response(content=result_content, view=None)
        except Exception:
            logger.exception("Balloon launch failed")
            await interaction.edit_original_response(
                content="❌ The launch simulation failed. Please try again.",
                view=None,
            )


@bot.command(name="launch")
async def cmd_launch(ctx):
    view = BalloonConfigurator()
    content = view._build_config_text()
    msg = await ctx.send(content, view=view)
    view._msg = msg


@bot.command(name="physics")
async def cmd_physics(ctx):
    content = (
        "⚙️ **Physics Model**\n\n"
        "• ρ = P / (R_air × T)\n"
        "• F_buoy = ρ_air × g × V\n"
        "• F_drag = 0.5 × ρ × v² × C_d × A\n"
        "• PV = nRT\n"
        "• Fixed-step Euler: Δt = 0.5s"
    )
    await ctx.send(content)


@bot.command(name="help")
async def cmd_help(ctx):
    content = (
        "🎈 **Balloon Frontier**\n\n"
        "• `/launch` — Open the balloon configurator\n"
        "• `/physics` — View the physics equations\n"
        "• `/help` — This message"
    )
    await ctx.send(content)


def run_bot():
    token = os.environ.get("DISCORD_BF_TOKEN") or os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
