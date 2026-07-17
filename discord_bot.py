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

logger = logging.getLogger("balloon_frontier_bot")

# ─── Game Data ────────────────────────────────────────────────────────

GAS_OPTIONS = {
    "helium": ("Helium", 0.0040026, 5),
    "hydrogen": ("Hydrogen", 0.002016, 3),
    "hot_air": ("Hot Air", 0.02897, 1),
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


# ─── Simulation ───────────────────────────────────────────────────────

def run_simulation(gas_type, gas_mass, gas_temp, payload_mass,
                    drag_coeff, envelope_vol, stretch_ratio):
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

    return telemetry, {"peak_altitude": peak_alt, "burst": burst}


def make_result_embed(gas_name, gas_mass, env_name, payload_name, site_name,
                      telemetry, summary):
    """Build result embed for a launch."""
    peak = summary["peak_altitude"]
    burst = summary["burst"]
    target = 30000
    status = "🟢" if peak >= target else "🟡" if peak >= target * 0.7 else "🔵"

    lines = ["🎈 **Launch Report**\n"]
    lines.append(f"Gas: {gas_name} | Mass: {gas_mass}kg")
    lines.append(f"Envelope: {env_name}")
    lines.append(f"Site: {site_name}\n")
    lines.append(f"Altitude: {status} {peak:,.0f}m / {target:,}m target")
    lines.append(f"Burst: {'💥 Yes' if burst else '🟢 No'}\n")

    # Telemetry
    sampled = telemetry[::1]
    for r in sampled[:25]:
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


# ─── Configurator — stateful menu ─────────────────────────────────

class BalloonConfigurator(discord.ui.View):
    """View with select menus + launch button."""

    # Class-level option builders
    def __init__(self):
        super().__init__(timeout=300)

        # Initialize config state
        self.state = {
            "gas": "helium",
            "gas_mass": 2.0,
            "envelope": "latex",
            "payloads": ["none"],
            "site": "field",
        }
        self._msg = None

        # Build and add all menus
        self._add_menu("gas", "Select gas type",
            _make_options(GAS_OPTIONS))
        self._add_menu("envelope", "Select envelope",
            _make_options(ENVELOPE_OPTIONS))
        self._add_menu("payloads", "Select payloads",
            _make_options(PAYLOAD_OPTIONS), allow_multi=True)
        self._add_menu("site", "Select launch site",
            _make_options(SITE_OPTIONS))

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

    def _build_config_text(self):
        """Build a text summary of current config."""
        s = self.state
        gas = GAS_OPTIONS[s["gas"]]
        env = ENVELOPE_OPTIONS[s["envelope"]]
        site = SITE_OPTIONS[s["site"]]
        payloads = [PAYLOAD_OPTIONS[p] for p in s["payloads"]]
        payload_names = [p[0] for p in payloads]
        payload_mass = sum(p[1] for p in payloads)

        lines = ["🎈 **Balloon Configuration**\n"]
        lines.append(f"Gas: {gas[0]} — {s['gas_mass']} kg")
        lines.append(f"Envelope: {env[0]} — {env[1]}m³")
        lines.append(f"Payloads: {', '.join(payload_names)}")
        lines.append(f"Site: {site[0]}")
        lines.append(f"Total mass: {s['gas_mass'] + env[2] + payload_mass:.1f} kg\n")
        lines.append("Use the dropdowns to configure, then tap Launch.")
        return "\n".join(lines)

    def _handle_select(self, interaction, key, value):
        """Handle a dropdown selection update."""
        if key == "payloads":
            self.state["payloads"] = value
        else:
            self.state[key] = value[0] if value else self.state[key]

    async def _update_message(self, interaction):
        """Update the message with current config."""
        content = self._build_config_text()
        if self._msg is None:
            self._msg = interaction
        await self._msg.edit(content=content, view=self)


def _make_options(options_dict):
    """Build discord.SelectOption list from a dict."""
    opts = []
    for k, v in options_dict.items():
        opts.append(discord.SelectOption(value=k, label=v[0], description="select"))
    return opts


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
        if self._parent._msg:
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

        try:
            tel, summary = run_simulation(
                state["gas"], state["gas_mass"], 288.15, payload_mass,
                env_info[3], env_info[1], env_info[4]
            )
            result = make_result_embed(
                gas_info[0], state["gas_mass"], env_info[0],
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
