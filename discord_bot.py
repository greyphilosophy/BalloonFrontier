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
from balloon_frontier.simulation import (
    run_simulation,
    EnvelopeConfig,
    SimulationState,
)
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


# ─── Simulation ───────────────────────────────────────────────────────

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


def _run_simulation_thread(state: SimulationState, has_pressure_valve):
    """Run simulation in thread to avoid blocking event loop."""
    _ensure_missions_loaded()
    state.has_pressure_valve = has_pressure_valve
    tel = run_simulation(state, dt=0.1, total_time_s=43200.0, max_steps=300000, step_interval=1.0)
    
    if not tel:
        return [], {
            "peak_altitude": 0,
            "time_of_flight": 0,
            "burst": False,
            "landed": False,
            "crashed": False,
        }
    
    last = tel[-1]
    peak_altitude = max(t.get("altitude_m", 0) for t in tel)
    flight_time = last.get("time_s", 0)
    burst = last.get("burst", False)
    landed = last.get("landed", False)
    crashed = last.get("crashed", False)
    
    return tel, {
        "peak_altitude": peak_altitude,
        "time_of_flight": flight_time,
        "burst": burst,
        "landed": landed,
        "crashed": crashed,
    }


def format_score_breakdown(score, peak_alt, payload_count, time_of_flight):
    """Format the score breakdown for the final result."""
    lines = []
    lines.append(f"**Score Breakdown**")
    lines.append(f"- Peak Altitude: {peak_alt:.0f}m ({score['peak_alt']} pts)")
    lines.append(f"- Flight Time: {time_of_flight:.0f}s ({score['time']} pts)")
    lines.append(f"- Payload Bonus: {payload_count} ({score['payload']} pts)")
    lines.append(f"**Total Score: {score['total']}**")
    return "\n".join(lines)


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


# ─── Configurator — interactive walkthrough ─────────────────────────

class _StepConfigurator(discord.ui.View):
    """Step-by-step interactive walkthrough for balloon configuration.
    
    Replaces stacked dropdown menus with numbered buttons presented one step
    at a time. Each step auto-advances to the next (except payloads which
    allow toggling without advancing).
    """

    # Step constants
    STEP_GAS = 0
    STEP_ENVELOPE = 1
    STEP_FILL = 2
    STEP_PAYLOADS = 3
    STEP_SITE = 4
    STEP_REVIEW = 5

    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx  # Store the context for message updates
        
        # Config state
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
        self._current_step = self.STEP_GAS
        self._msg = None

        # Add the launch button (always present)
        self.add_item(_LaunchButton(self))

    def _build_step_message(self):
        """Build the message content for the current step."""
        step = self._current_step
        step_label = self._get_step_label(step)
        
        lines = [f"🔧 **Balloon Configuration**\n", f"**Step {step + 1}/6:** {step_label}\n"]
        
        # Add context if not first step
        if step > self.STEP_GAS:
            lines.append(f"Current: {self._get_current_config_summary()}")
            lines.append("")
        
        # Add options based on current step
        if step == self.STEP_GAS:
            for i, (key, val) in enumerate(GAS_OPTIONS.items(), 1):
                lines.append(f"{i}. {val[0]} (ρ={val[1]} kg/m³, ${val[2]}/kg)")
        elif step == self.STEP_ENVELOPE:
            for i, (key, val) in enumerate(ENVELOPE_OPTIONS.items(), 1):
                lines.append(f"{i}. {val[0]} ({val[1]}m³)")
        elif step == self.STEP_FILL:
            for i, (key, info) in enumerate(FILL_MODES.items(), 1):
                lines.append(f"{i}. {info['label']}")
                lines.append(f"   {info['description']}")
        elif step == self.STEP_PAYLOADS:
            for i, (key, val) in enumerate(PAYLOAD_OPTIONS.items(), 1):
                selected = "✓" if key in self.state["payloads"] else " "
                lines.append(f"{i}. [{selected}] {val[0]} ({val[1]}kg, ${val[2]})")
        elif step == self.STEP_SITE:
            for i, (_, val) in enumerate(SITE_OPTIONS.items(), 1):
                lines.append(f"{i}. {val.name}")
                lines.append(f"   {val.description}")
        
        lines.append("")
        if step < self.STEP_REVIEW:
            lines.append("Click a button to select → Auto-advances to next step")
        else:
            lines.append("Review looks good? Click **Launch**! 🚀")
        
        return "\n".join(lines)

    def _get_step_label(self, step):
        """Get the label for a step."""
        labels = {
            self.STEP_GAS: "Choose Gas Type",
            self.STEP_ENVELOPE: "Choose Envelope",
            self.STEP_FILL: "Choose Fill Mode",
            self.STEP_PAYLOADS: "Choose Payloads",
            self.STEP_SITE: "Choose Launch Site",
            self.STEP_REVIEW: "Review & Launch",
        }
        return labels.get(step, "Unknown")

    def _get_current_config_summary(self):
        """Get a summary of current configuration."""
        s = self.state
        gas = GAS_OPTIONS[s["gas"]][0]
        env = ENVELOPE_OPTIONS[s["envelope"]][0]
        fill = FILL_MODES[s["fill_mode"]]["label"]
        payloads = ", ".join([PAYLOAD_OPTIONS[p][0] for p in s["payloads"]])
        site = SITE_OPTIONS[s["site"]].name
        
        return f"Gas: {gas} | Envelope: {env} | Fill: {fill}\nPayloads: {payloads} | Site: {site}"

    def _compute_gas_mass(self):
        """Compute gas mass based on current fill_mode, envelope, and gas."""
        gas_type = self.state["gas"]
        env_id = self.state["envelope"]
        fill_mode = self.state["fill_mode"]
        
        env_info = ENVELOPE_OPTIONS[env_id]
        volume = env_info[1]
        
        # Pass envelope + site context to the shared fill functions.
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

    def _get_env_params(self):
        """Build envelope + site params to pass to shared fill functions."""
        env_id = self.state["envelope"]
        site = SITE_OPTIONS[self.state["site"]]
        site_cond = site.derive_conditions()
        return {
            "envelope_type": env_id,
            "launch_altitude": site_cond.get("launch_altitude"),
            "launch_pressure": site_cond.get("launch_pressure"),
            "gas_temperature": site_cond.get("gas_temperature"),
        }

    def _handle_gas_select(self, interaction, index: int):
        """Handle gas type selection."""
        gas_keys = list(GAS_OPTIONS.keys())
        if 0 < index <= len(gas_keys):
            self.state["gas"] = gas_keys[index - 1]
            self.state["gas_mass"] = self._compute_gas_mass()
        
        # Advance to next step
        self._advance_step()

    def _handle_envelope_select(self, interaction, index: int):
        """Handle envelope selection."""
        env_keys = list(ENVELOPE_OPTIONS.keys())
        if 0 < index <= len(env_keys):
            self.state["envelope"] = env_keys[index - 1]
            self.state["gas_mass"] = self._compute_gas_mass()
        
        self._advance_step()

    def _handle_fill_select(self, interaction, index: int):
        """Handle fill mode selection."""
        fill_keys = list(FILL_MODES.keys())
        if 0 < index <= len(fill_keys):
            self.state["fill_mode"] = fill_keys[index - 1]
            self.state["gas_mass"] = self._compute_gas_mass()
        
        self._advance_step()

    def _handle_payload_select(self, interaction, index: int):
        """Handle payload selection (toggle without advancing)."""
        payload_keys = list(PAYLOAD_OPTIONS.keys())
        if 0 < index <= len(payload_keys):
            key = payload_keys[index - 1]
            
            if key == "none":
                # Selecting "none" clears all payloads
                self.state["payloads"] = ["none"]
            else:
                # Toggle payload
                if "none" in self.state["payloads"]:
                    self.state["payloads"] = [key]
                elif key in self.state["payloads"]:
                    self.state["payloads"].remove(key)
                    if not self.state["payloads"]:
                        self.state["payloads"] = ["none"]
                else:
                    self.state["payloads"].append(key)
            
            self.state["gas_mass"] = self._compute_gas_mass()
            # Don't advance - allow multiple selections
            self._update_message()

    def _handle_site_select(self, interaction, index: int):
        """Handle site selection."""
        site_keys = list(SITE_OPTIONS.keys())
        if 0 < index <= len(site_keys):
            self.state["site"] = site_keys[index - 1]
            self.state["gas_mass"] = self._compute_gas_mass()
        
        self._advance_step()

    def _advance_step(self):
        """Advance to the next step."""
        self._current_step += 1
        if self._current_step > self.STEP_REVIEW:
            self._current_step = self.STEP_REVIEW
        self._update_message()

    def _update_message(self):
        """Update the message with current step content."""
        if self._msg is not None:
            content = self._build_step_message()
            view = self._build_view()
            try:
                self._msg.edit(content=content, view=view)
            except discord.errors.NotFound:
                pass

    def _build_view(self):
        """Build the view with buttons for the current step."""
        view = _StepConfiguratorView(self)
        return view

    async def on_timeout(self):
        """Handle timeout."""
        try:
            if self._msg is not None:
                await self._msg.edit(content=self._msg.content + "\n\n⏰ Timed out. Use `/launch` to start over.", view=None)
        except discord.errors.NotFound:
            pass


class _StepConfiguratorView(discord.ui.View):
    """The View that holds the buttons for a step."""
    
    def __init__(self, parent: _StepConfigurator):
        super().__init__(timeout=300)
        self.parent = parent
        self._current_step = parent._current_step
        
        # Add step-specific buttons
        if self._current_step == parent.STEP_GAS:
            for i, (key, val) in enumerate(GAS_OPTIONS.items(), 1):
                self.add_item(_OptionButton(str(i), f"Choose {val[0]}", 
                    lambda interaction, idx=i: parent._handle_gas_select(interaction, idx)))
        
        elif self._current_step == parent.STEP_ENVELOPE:
            for i, (key, val) in enumerate(ENVELOPE_OPTIONS.items(), 1):
                self.add_item(_OptionButton(str(i), f"Choose {val[0]}",
                    lambda interaction, idx=i: parent._handle_envelope_select(interaction, idx)))
        
        elif self._current_step == parent.STEP_FILL:
            for i, (key, info) in enumerate(FILL_MODES.items(), 1):
                self.add_item(_OptionButton(str(i), info["label"],
                    lambda interaction, idx=i: parent._handle_fill_select(interaction, idx)))
        
        elif self._current_step == parent.STEP_PAYLOADS:
            for i, (key, val) in enumerate(PAYLOAD_OPTIONS.items(), 1):
                self.add_item(_PayloadButton(str(i), f"Toggle {val[0]}", 
                    lambda interaction, idx=i: parent._handle_payload_select(interaction, idx)))
            self.add_item(_LaunchButton(parent))
        
        elif self._current_step == parent.STEP_SITE:
            for i, (_, val) in enumerate(SITE_OPTIONS.items(), 1):
                self.add_item(_OptionButton(str(i), val.name,
                    lambda interaction, idx=i: parent._handle_site_select(interaction, idx)))
            self.add_item(_LaunchButton(parent))
        
        elif self._current_step == parent.STEP_REVIEW:
            self.add_item(_LaunchButton(parent))


class _OptionButton(discord.ui.Button):
    """A numbered option button."""
    
    def __init__(self, index: str, label: str, callback):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"step_{index}")
        self._callback = callback
    
    async def callback(self, interaction: discord.Interaction):
        await self._callback(interaction)


class _PayloadButton(discord.ui.Button):
    """A payload toggle button."""
    
    def __init__(self, index: str, label: str, callback):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, custom_id=f"payload_{index}")
        self._callback = callback
    
    async def callback(self, interaction: discord.Interaction):
        await self._callback(interaction)


class _LaunchButton(discord.ui.Button):
    def __init__(self, parent, label="🚀 Launch", callback=None):
        super().__init__(label=label, style=discord.ButtonStyle.success)
        self._parent = parent
    
    async def callback(self, interaction: discord.Interaction):
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
            
            site_cond = self._parent._get_env_params()
            
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
            
            # Build simulation state
            env = EnvelopeConfig(
                max_volume_m3=env_info[1],
                burst_stretch_ratio=env_info[4],
                drag_coefficient=env_info[3],
                permeability=0.001,
                mass_kg=0.5,  # envelope mass placeholder
                contained_gas=True,
            )
            
            sim_state = SimulationState(
                gas_type=state["gas"],
                gas_mass_kg=gas_mass,
                envelope=env,
                payload_mass_kg=payload_mass,
                ballast_mass_kg=0.0,
                terrain_base_altitude_offset_m=0.0,
                gas_temperature_k=site_cond["gas_temperature"],
                has_pressure_valve=has_pressure_valve,
            )
            
            # Run the CPU-heavy simulation off the event loop.
            tel = await asyncio.to_thread(
                _run_simulation_thread,
                sim_state, has_pressure_valve,
            )
            
            # Build summary from telemetry
            if tel:
                last = tel[-1]
                peak_altitude = max(t.get("altitude_m", 0) for t in tel)
                flight_time = last.get("time_s", 0)
                burst = last.get("burst", False)
                landed = last.get("landed", False)
                crashed = last.get("crashed", False)
                summary = {
                    "peak_altitude": peak_altitude,
                    "time_of_flight": flight_time,
                    "burst": burst,
                    "landed": landed,
                    "crashed": crashed,
                }
            else:
                summary = {"peak_altitude": 0, "time_of_flight": 0, "burst": False, "landed": False, "crashed": False}
            
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
    view = _StepConfigurator(ctx)
    content = view._build_step_message()
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