"""Balloon Frontier — Discord Bot

Interactive select-menu UI for the balloon simulation game.
Uses the Python physics engine (`balloon_frontier/physics.py`).
"""

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
    calculate_optimal_fill,
    FillMode,
)
from balloon_frontier.ascii_chart import chart_to_string
from balloon_frontier.mission_selection import (
    assign_missions_to_flight,
    seed_from_game_state,
    choose_mission_count,
)
from balloon_frontier.flight_score import calculate_flight_score
from balloon_frontier.medal_tier import get_medal_tier, get_medal_emoji, medal_tier_to_string

logger = logging.getLogger("balloon_frontier_bot")

# ─── Game Data ────────────────────────────────────────────────────────

GAS_OPTIONS = {
    "helium": ("Helium", 0.0040026, 5),
    "hydrogen": ("Hydrogen", 0.002016, 3),
    "hot_air": ("Hot Air", 0.0289652068, 1),
    "methane": ("Methane", 0.01604, 4),
}

ENVELOPE_OPTIONS = {
    "mylar": ("Mylar Party Balloon", 0.5, 0.05, 2.0, 0.47, 500),
    "latex": ("Latex Weather Balloon", 10.0, 1.0, 3.0, 0.47, 2000),
    "zero_pressure": ("Zero-Pressure Polyethylene", 100.0, 18.0, 1.5, 0.47, 15000),
    "blimp": ("Small Non-Rigid Blimp", 500.0, 45.0, 1.3, 0.55, 50000),
}

PAYLOAD_OPTIONS = {
    "camera": ("Camera", 1.5, 500),
    "radio": ("Radio Repeater", 2.0, 800),
    "weather_sensor": ("Weather Sensor", 0.8, 1200),
    "battery": ("Battery Pack", 3.0, 1000),
    "heater": ("Heater", 2.5, 750),
    "ballast": ("Ballast (Sand)", 15.0, 300),
    "parachute": ("Parachute", 2.0, 600),
    "flight_computer": ("Flight Computer", 1.2, 2000),
    "none": ("None", 1.0, 100),
}

SITE_OPTIONS = {
    "field": ("Open Field", 0, 0, 2.0, "Flat terrain, mild crosswind"),
    "mountain": ("Mountain Ridge", 1500, -5, 4.0, "Elevated, colder, stronger wind"),
    "rooftop": ("Urban Rooftop", 50, 3, 3.0, "Warm microclimate, moderate wind"),
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

def run_simulation(
    gas_type,
    gas_mass,
    gas_temp,
    payload_mass,
    drag_coeff,
    envelope_vol,
    stretch_ratio,
    *,
    mission_assignment=None,
):
    """Run fixed-step vertical simulation. Returns (telemetry, summary)."""
    alt = 0.0
    vel = 0.0
    burst = False
    peak_alt = 0.0
    telemetry = []
    G = 9.80665

    for step in range(80000):
        t_s = step * 0.5
        temp_amb = atmosphere_temperature(alt)
        pressure = atmosphere_pressure(alt)
        rho_air = atmosphere_density(alt)

        vol = gas_volume(gas_mass, gas_type, gas_temp, pressure)
        burst_vol = envelope_vol * stretch_ratio

        if not burst and vol >= burst_vol:
            burst = True
            vol = burst_vol

        area = spherical_area(min(vol, burst_vol))
        F_buoy = buoyant_force(gas_type, gas_mass, gas_temp, alt)
        F_weight = (gas_mass + payload_mass) * G
        F_drag = drag_force(vel, alt, drag_coeff, area)

        total_mass = gas_mass + payload_mass
        acc = (F_buoy - F_weight - F_drag) / total_mass

        if burst:
            vel *= 0.95

        vel += acc * 0.5
        alt += vel * 0.5
        gas_temp = temp_amb

        if alt > peak_alt:
            peak_alt = alt

        if step % 4000 == 0:
            telemetry.append({"time": t_s, "alt": alt, "vel": vel})

        if burst and alt < 200:
            break
        if alt < -100:
            break

    flight_time = telemetry[-1]["time"] if telemetry else 0

    # Post-flight scoring + medal determination.
    # The Discord UI doesn't currently expose payload count directly,
    # so we default to scoring as 1 payload.
    payload_count = 1
    score = calculate_flight_score(peak_alt, payload_count, flight_time)
    medal_name = medal_tier_to_string(peak_alt)
    medal_emoji = get_medal_emoji(peak_alt)

    summary = {
        "peak_altitude": peak_alt,
        "burst": burst,
        "time_of_flight": flight_time,
        "payload_count": payload_count,
        "score": score,
        "medal": medal_name,
        "medal_emoji": medal_emoji,
    }

    # Flight/session mission assignment for later evaluation + UI.
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


# ─── Configurator — stateful menu ─────────────────────────────────

class BalloonConfigurator(discord.ui.View):
    """View with select menus + launch button."""

    def __init__(self):
        super().__init__(timeout=300)

        # Initialize config state
        self.state = {
            "gas": "helium",
            "envelope": "latex",
            "payloads": ["none"],
            "site": "field",
            # Fill mode: Auto/Light/Normal/Heavy/Manual
            "fill_mode": "auto",
            # Player-entered gas mass for Manual mode.
            # When Auto or a preset is active, this must be ignored.
            "manual_gas_mass": None,
            # Cached computed gas mass (kg) for the current gas+envelope+fill_mode.
            # Tests (and the UI) expect this to be present in state.
            "gas_mass": None,
        }
        # Initialize cached gas mass from defaults.
        self.state["gas_mass"] = self._compute_gas_mass()
        self._msg = None

        # Build and add all menus
        self._add_menu("gas", "Select gas type",
            _make_options(GAS_OPTIONS))
        self._add_menu("envelope", "Select envelope",
            _make_options(ENVELOPE_OPTIONS))
        self._add_menu("fill_mode", "Select fill mode",
            _make_fill_mode_options())
        self._add_menu("payloads", "Select payloads",
            _make_options(PAYLOAD_OPTIONS), allow_multi=True)
        self._add_menu("site", "Select launch site",
            _make_options(SITE_OPTIONS))

        # Note: we intentionally do not add a separate Discord UI control for
        # manual gas mass here, to avoid exceeding Discord's component layout
        # limits in tests.

    def _add_menu(self, key, placeholder, options, allow_multi=False):
        if allow_multi:
            menu = _Select(self, key, placeholder, options, multi=True)
        else:
            menu = _Select(self, key, placeholder, options, multi=False)
        self.add_item(menu)

    def _add_button(self, label, callback_func):
        btn = _LaunchButton(self, label, callback_func)
        self.add_item(btn)
        return btn

    def _handle_select(self, interaction, key, value):
        """Handle a dropdown selection update."""
        if key == 'payloads':
            self.state['payloads'] = value
            return

        # Single-select dropdowns pass a list (discord Select values).
        self.state[key] = value[0] if value else self.state[key]

        # Cache gas mass when the inputs that affect it change.
        if key in ('gas', 'envelope', 'fill_mode'):
            self.state['gas_mass'] = self._compute_gas_mass()

    def _compute_gas_mass(self):
        """Compute gas mass based on current fill_mode, envelope, and gas.

        Uses balloon_frontier.fill.apply_fill_mode so Auto/Light/Normal/Heavy
        inherit burst-safe clamping from the launch state machine.
        """
        gas_type = self.state["gas"]
        env_id = self.state["envelope"]
        fill_mode = self.state["fill_mode"]

        env_info = ENVELOPE_OPTIONS[env_id]
        volume = env_info[1]

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
                # Default to the maximum burst-safe mass.
                manual_mass = calculate_max_safe_gas_mass(volume, gas_type)
                self.state["manual_gas_mass"] = manual_mass
            mass = apply_fill_mode(volume, gas_type, FillMode.MANUAL, manual_mass_kg=manual_mass)
        else:
            # Override any manual entry whenever Auto/preset is active.
            mass = apply_fill_mode(volume, gas_type, mode)

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

        # Use cached gas mass so UI state persists across transitions.
        gas_mass = self.state.get("gas_mass")
        if gas_mass is None:
            gas_mass = self._compute_gas_mass()
            self.state["gas_mass"] = gas_mass
        fill_label = FILL_MODES[s["fill_mode"]]["label"]

        lines = ["🎈 **Balloon Configuration**\n"]
        lines.append(f"Gas: {gas[0]}")
        lines.append(f"Fill: {fill_label} → {gas_mass:.3f} kg")
        lines.append(f"Envelope: {env[0]} — {env[1]}m³")
        lines.append(f"Payloads: {', '.join(payload_names)}")
        lines.append(f"Site: {site[0]}")
        lines.append(f"Total mass: {gas_mass + env[2] + payload_mass:.1f} kg\n")
        lines.append("Use the dropdowns to configure, then tap Launch.")
        return "\n".join(lines)


def _make_options(options_dict):
    """Build discord.SelectOption list from a dict."""
    opts = []
    for k, v in options_dict.items():
        opts.append(discord.SelectOption(value=k, label=v[0], description="select"))
    return opts


def _make_fill_mode_options():
    """Build select options for fill mode presets."""
    opts = []
    for mode, info in FILL_MODES.items():
        opts.append(discord.SelectOption(
            value=mode,
            label=info["label"],
            description=info["description"],
        ))
    return opts


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

        # If the player is currently in manual mode, recache gas_mass.
        if self._parent.state.get("fill_mode") == "manual":
            self._parent.state["gas_mass"] = self._parent._compute_gas_mass()

        # Update the existing config message.
        if getattr(self._parent, "_msg", None) is not None:
            new_content = self._parent._build_config_text()
            await self._parent._msg.edit(content=new_content, view=self._parent)

        await interaction.response.send_message(
            "✅ Manual gas mass updated.",
            ephemeral=True,
        )


class _ManualGasMassButton(discord.ui.Button):
    """Button that opens the manual gas mass modal."""

    def __init__(self, parent: "BalloonConfigurator"):
        super().__init__(
            label="Set Manual Mass",
            style=discord.ButtonStyle.secondary,
        )
        self._parent = parent

    async def callback(self, interaction: discord.Interaction):
        modal = _ManualGasMassModal(self._parent)
        await interaction.response.send_modal(modal)


class _Select(discord.ui.Select):
    """Generic dropdown that updates the parent view's state."""
    def __init__(self, parent, key, placeholder, options, multi):
        if multi:
            super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=3)
        else:
            super().__init__(placeholder=placeholder, options=options)
        self._parent = parent
        self._key = key

    async def callback(self, interaction):
        self._parent._handle_select(interaction, self._key, self.values)

        # For Manual fill, immediately collect the player's gas mass.
        if self._key == "fill_mode" and self._parent.state.get("fill_mode") == "manual":
            modal = _ManualGasMassModal(self._parent)
            await interaction.response.send_modal(modal)
            return

        new_content = self._parent._build_config_text()
        await self._parent._msg.edit(content=new_content, view=self._parent)


class _LaunchButton(discord.ui.Button):
    def __init__(self, parent, label, callback):
        super().__init__(label=label, style=discord.ButtonStyle.success)
        self._parent = parent

    async def callback(self, interaction):
        state = self._parent.state
        gas_info = GAS_OPTIONS[state["gas"]]
        env_info = ENVELOPE_OPTIONS[state["envelope"]]
        site_info = SITE_OPTIONS[state["site"]]
        payloads = [PAYLOAD_OPTIONS[p] for p in state["payloads"]]
        payload_names = [p[0] for p in payloads]
        payload_mass = sum(p[1] for p in payloads)

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

            tel, summary = run_simulation(
                state["gas"], gas_mass, 288.15, payload_mass,
                env_info[3], env_info[1], env_info[4],
                mission_assignment=mission_assignment,
            )
            result = make_result_embed(
                gas_info[0], gas_mass, env_info[0],
                " + ".join(payload_names), site_info[0],
                tel, summary
            )
            # Truncate if too long
            if len(result) > 1900:
                result = result[:1897] + "..."
            await interaction.response.send_message(result, ephemeral=False)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}")


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
