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
    run_simulation as _run_sim_core,
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
    "light": {"label": "Light", "description": "Less free lift — slower ascent, higher burst"},
    "normal": {"label": "Normal", "description": "Baseline optimal fill"},
    "heavy": {"label": "Heavy", "description": "More free lift — faster ascent, earlier burst"},
    "manual": {"label": "Manual", "description": "Your chosen gas mass"},
}


# ─── Simulation ───────────────────────────────────────────────────────

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
    tel = _run_sim_core(state, dt=0.1, total_time_s=43200.0, max_steps=300000, step_interval=1.0)
    
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


class _ManualGasMassModal(discord.ui.Modal):
    """Modal to set the manual gas mass (kg)."""

    def __init__(self, parent: "_StepConfigurator"):
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
            new_content = self._parent._build_step_message()
            view = self._parent._build_view()
            try:
                await self._parent._msg.edit(content=new_content, view=view)
            except discord.errors.NotFound:
                pass

        await interaction.response.send_message(
            "✅ Manual gas mass updated.",
            ephemeral=True,
        )


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
        # Add back button (always present, but we rebuild view per step)
        self.add_item(_BackButton(self))
        # Build initial step buttons
        self._build_current_buttons()

    # ── Step rendering ────────────────────────

    async def _send_step(self, interaction=None):
        """Send or edit the message with current step content."""
        content = self._build_step_message()
        
        if interaction is not None:
            try:
                await interaction.response.edit_message(content=content, view=self)
            except (discord.errors.NotFound, discord.errors.InteractionResponded):
                try:
                    await interaction.edit_original_response(content=content, view=self)
                except discord.errors.NotFound:
                    pass
        elif self._msg is not None:
            try:
                await self._msg.edit(content=content, view=self)
            except discord.errors.NotFound:
                pass

    def _build_current_buttons(self):
        """Clear and rebuild buttons for the current step only."""
        self.clear_items()
        # Re-add persistent buttons
        self.add_item(_BackButton(self))
        self.add_item(_LaunchButton(self))
        # Add step-specific buttons
        self._add_step_buttons()

    def _add_step_buttons(self):
        """Add buttons specific to the current step."""
        step = self._current_step
        if step == self.STEP_GAS:
            for i, (key, val) in enumerate(GAS_OPTIONS.items(), 1):
                self.add_item(_OptionButton(i, val[0], self._on_gas))
        elif step == self.STEP_ENVELOPE:
            for i, (key, val) in enumerate(ENVELOPE_OPTIONS.items(), 1):
                self.add_item(_OptionButton(i, val[0], self._on_envelope))
        elif step == self.STEP_FILL:
            for i, (key, info) in enumerate(FILL_MODES.items(), 1):
                self.add_item(_OptionButton(i, info["label"], self._on_fill))
        elif step == self.STEP_PAYLOADS:
            for i, (key, val) in enumerate(PAYLOAD_OPTIONS.items(), 1):
                self.add_item(_PayloadButton(i, val[0], self._on_payload))
            if self.state.get("fill_mode") == "manual":
                self.add_item(_ManualGasMassButton(self))
        elif step == self.STEP_SITE:
            for i, (_, val) in enumerate(SITE_OPTIONS.items(), 1):
                self.add_item(_OptionButton(i, val.name, self._on_site))

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

    def _option_by_index(self, index: int, options_dict):
        """Resolve a 1-based index to a key string from the dict."""
        keys = list(options_dict.keys())
        if 0 < index <= len(keys):
            return keys[index - 1]
        return None

    # ── Handler methods (must be async) ──────────────────────────

    async def _on_gas(self, interaction, index):
        selected = self._option_by_index(index, GAS_OPTIONS)
        if selected is not None:
            self.state["gas"] = selected
            self.state["gas_mass"] = self._compute_gas_mass()
        self._current_step += 1
        if self._current_step > self.STEP_REVIEW:
            self._current_step = self.STEP_REVIEW
        self._build_current_buttons()
        await self._send_step(interaction)

    async def _on_envelope(self, interaction, index):
        selected = self._option_by_index(index, ENVELOPE_OPTIONS)
        if selected is not None:
            self.state["envelope"] = selected
            self.state["gas_mass"] = self._compute_gas_mass()
        self._current_step += 1
        if self._current_step > self.STEP_REVIEW:
            self._current_step = self.STEP_REVIEW
        self._build_current_buttons()
        await self._send_step(interaction)

    async def _on_fill(self, interaction, index):
        selected = self._option_by_index(index, FILL_MODES)
        if selected is not None:
            self.state["fill_mode"] = selected
            self.state["gas_mass"] = self._compute_gas_mass()
            # If Manual, open modal for gas mass entry
            if selected == "manual":
                modal = _ManualGasMassModal(self)
                await interaction.response.send_modal(modal)
                return
        self._current_step += 1
        if self._current_step > self.STEP_REVIEW:
            self._current_step = self.STEP_REVIEW
        self._build_current_buttons()
        await self._send_step(interaction)

    async def _on_payload(self, interaction, index):
        """Handle payload selection (toggle without advancing)."""
        key = self._option_by_index(index, PAYLOAD_OPTIONS)
        if key is None:
            return
        
        if key == "none":
            self.state["payloads"] = ["none"]
        else:
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
        await self._send_step(interaction)

    async def _on_site(self, interaction, index):
        selected = self._option_by_index(index, SITE_OPTIONS)
        if selected is not None:
            self.state["site"] = selected
            self.state["gas_mass"] = self._compute_gas_mass()
        self._current_step += 1
        if self._current_step > self.STEP_REVIEW:
            self._current_step = self.STEP_REVIEW
        self._build_current_buttons()
        await self._send_step(interaction)

    async def _on_back(self, interaction):
        """Go back to previous step."""
        if self._current_step > self.STEP_GAS:
            self._current_step -= 1
            self._build_current_buttons()
            await self._send_step(interaction)

    def _build_view(self):
        """Build the view with buttons for the current step."""
        view = self  # We modify self
        return view

    async def on_timeout(self):
        """Handle timeout."""
        try:
            if self._msg is not None:
                await self._msg.edit(
                    content=self._msg.content + "\n\n⏰ Timed out. Use `/launch` to start over.",
                    view=None,
                )
        except discord.errors.NotFound:
            pass


class _OptionButton(discord.ui.Button):
    """A numbered option button. Stores the index and handler directly."""
    
    def __init__(self, index: int, label: str, handler):
        super().__init__(
            label=str(index),
            style=discord.ButtonStyle.primary,
            custom_id=f"cfg_option_{index}",
        )
        self._index = index
        self._handler = handler

    async def callback(self, interaction: discord.Interaction):
        await self._handler(interaction, self._index)


class _PayloadButton(discord.ui.Button):
    """A payload toggle button."""
    
    def __init__(self, index: int, label: str, handler):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            custom_id=f"payload_{index}",
        )
        self._index = index
        self._handler = handler

    async def callback(self, interaction: discord.Interaction):
        await self._handler(interaction, self._index)


class _BackButton(discord.ui.Button):
    """Back button for navigation."""
    
    def __init__(self, parent: _StepConfigurator):
        super().__init__(
            label="← Back",
            style=discord.ButtonStyle.secondary,
            custom_id="cfg_back",
            disabled=(parent._current_step <= 0),  # Can't go before step 1
        )
        self._parent = parent

    async def callback(self, interaction: discord.Interaction):
        await self._parent._on_back(interaction)


class _ManualGasMassButton(discord.ui.Button):
    """Button that opens the manual gas mass modal."""

    def __init__(self, parent: _StepConfigurator):
        super().__init__(
            label="Set Manual Mass",
            style=discord.ButtonStyle.secondary,
        )
        self._parent = parent

    async def callback(self, interaction: discord.Interaction):
        modal = _ManualGasMassModal(self._parent)
        await interaction.response.send_modal(modal)


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
            tel, summary = await asyncio.to_thread(
                _run_simulation_thread,
                sim_state, has_pressure_valve,
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


# ─── Backward Compatibility Layer ──────────────────────────────────
# Tests import the old API. This shim bridges them without duplicating logic.


def _get_default_state():
    """Return a fresh default state dict for BalloonConfigurator."""
    return {
        "gas": "helium",
        "envelope": "latex",
        "payloads": ["none"],
        "site": "field",
        "fill_mode": "auto",
        "manual_gas_mass": None,
        "gas_mass": None,
    }


class BalloonConfigurator:
    """Legacy compat wrapper around _StepConfigurator state machine."""

    timeout = 300  # Required by tests

    def __init__(self):
        self.state = _get_default_state()
        self.state["gas_mass"] = self._compute_gas_mass()

    # ── Data helpers ────────────────────────────────────────────

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

    def _get_site_conditions(self):
        """Legacy name — delegates to env_params."""
        return self._get_env_params()

    # ── Legacy public API ───────────────────────────────────────

    def _handle_select(self, interaction, key, values):
        """Legacy dropdown handler — sets state directly."""
        if key == 'payloads':
            self.state['payloads'] = values if isinstance(values, list) else [values]
            return
        # Single-select: values is a list, take first
        if isinstance(values, list):
            val = values[0] if values else self.state.get(key)
        else:
            val = values
        self.state[key] = val

        # Recompute gas_mass when relevant fields change
        if key in ('gas', 'envelope', 'fill_mode'):
            self.state['gas_mass'] = self._compute_gas_mass()

    def _build_config_text(self):
        """Legacy text summary — uses the same data as _build_step_message."""
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

        lines = ["🎈 **Balloon Configuration**\n"]
        lines.append(f"Gas: {gas[0]}")
        lines.append(f"Fill: {fill_label} → {gas_mass:.3f} kg")
        lines.append(f"Envelope: {env[0]} — {env[1]}m³")
        lines.append(f"Payloads: {', '.join(payload_names)}")
        lines.append(f"Site: {site.name}")
        lines.append(f"Total mass: {gas_mass + env[2] + payload_mass:.1f} kg\n")
        lines.append("Use the dropdowns to configure, then tap Launch.")
        return "\n".join(lines)


def _normalize_telemetry(tel):
    """Normalize telemetry keys to legacy format: time, alt, vel."""
    normalized = []
    for t in tel:
        entry = {}
        entry["time"] = t.get("time_s", t.get("time", 0))
        entry["alt"] = t.get("altitude_m", t.get("alt", 0))
        entry["vel"] = t.get("velocity_mps", t.get("vel", 0))
        entry["altitude_m"] = t.get("altitude_m", entry["alt"])
        entry["time_s"] = t.get("time_s", entry["time"])
        normalized.append(entry)
    return normalized


def _compute_summary(tel, mission_assignment=None):
    """Compute a legacy-style summary dict from telemetry."""
    if not tel:
        return {
            "peak_altitude": 0,
            "time_of_flight": 0,
            "burst": False,
            "landed": False,
            "crashed": False,
            "payload_count": 0,
            "score": 0.0,
            "medal": "None",
            "medal_emoji": "⚪",
            "assigned_missions": [],
            "mission_seed": 0,
            "mission_count": 0,
        }

    last = tel[-1]
    peak_altitude = max(t.get("altitude_m", 0) for t in tel)
    flight_time = last.get("time_s", 0)

    payload_count = 1  # default
    score = calculate_flight_score(peak_altitude, payload_count, flight_time)
    medal_tier = get_medal_tier(peak_altitude)
    medal_emoji = get_medal_emoji(peak_altitude)

    summary = {
        "peak_altitude": peak_altitude,
        "time_of_flight": flight_time,
        "burst": last.get("burst", False),
        "landed": last.get("landed", False),
        "crashed": last.get("crashed", False),
        "payload_count": payload_count,
        "score": score,
        "medal": medal_tier.name,
        "medal_emoji": medal_emoji,
        "telemetry": _normalize_telemetry(tel),
    }

    if mission_assignment is not None:
        summary["assigned_missions"] = mission_assignment.get("missions", [])
        summary["mission_seed"] = mission_assignment.get("seed", 0)
        summary["mission_count"] = mission_assignment.get("mission_count", 0)

    return summary


def run_simulation(gas_type, gas_mass, gas_temperature_k, payload_mass,
                   drag_coeff, volume, burst_stretch,
                   mission_assignment=None, weather_impacts=None,
                   has_pressure_valve=False):
    """Legacy sync wrapper so tests can call run_simulation(...) directly."""
    env = EnvelopeConfig(
        max_volume_m3=volume,
        burst_stretch_ratio=burst_stretch,
        drag_coefficient=drag_coeff,
        permeability=0.001,
        mass_kg=0.5,
        contained_gas=True,
    )
    state = SimulationState(
        gas_type=gas_type,
        gas_mass_kg=gas_mass,
        envelope=env,
        payload_mass_kg=payload_mass,
        ballast_mass_kg=0.0,
        terrain_base_altitude_offset_m=0.0,
        gas_temperature_k=gas_temperature_k,
        has_pressure_valve=has_pressure_valve,
    )
    # Use step_interval=1.0 for tests so telemetry fits in Discord's 2000 char limit
    raw_tel = _run_sim_core(state, dt=0.1, total_time_s=60.0, max_steps=600, step_interval=None)
    
    # Normalize telemetry to legacy keys for tests
    tel = _normalize_telemetry(raw_tel)

    return tel, _compute_summary(raw_tel, mission_assignment)


def make_result_embed(gas_name, gas_mass, env_name, payload_name, site_name,
                      tel=None, summary=None, telemetry=None):
    """Legacy compat function that formats telemetry into a Discord message.
    
    Accepts positional args (gas_name, gas_mass, ..., tel, summary) or
    keyword args (telemetry=, summary=) for test compatibility.
    """
    # Handle keyword-only calls like make_result_embed(gas_name=..., telemetry=..., summary=...)
    if tel is None:
        tel = []
    if summary is None:
        summary = {}
    
    tel_list = tel if isinstance(tel, list) else []
    
    # Support telemetry keyword arg
    if telemetry is not None and isinstance(telemetry, list):
        tel_list = telemetry
    
    # If first positional arg looks like a summary dict, swap
    if isinstance(tel, dict) and "peak_altitude" in tel:
        summary = tel
        tel_list = tel.get("telemetry", tel.get("telemetry_from_tel", []))
    
    peak_alt = summary.get("peak_altitude", 0)
    flight_time = summary.get("time_of_flight", 0)
    burst = summary.get("burst", False)
    landed = summary.get("landed", False)
    crashed = summary.get("crashed", False)
    payload_count = summary.get("payload_count", 1)
    score_val = summary.get("score", 0.0)
    if isinstance(score_val, float):
        score_val = int(score_val)
    medal_name = summary.get("medal", "None")
    medal_emoji = summary.get("medal_emoji", "⚪")

    # Status indicator
    if crashed:
        status_emoji = "🔴"
    elif burst:
        status_emoji = "🟡"  # yellow = caution/warning for burst
    elif landed:
        status_emoji = "🟢"  # green = safe landing
    else:
        status_emoji = "🔵"  # blue = flying

    alt_pts = int(peak_alt * 1.0)
    time_pts = int(flight_time * 100.0)
    pay_pts = int(payload_count * 500.0)

    lines = []
    lines.append(f"🎈 **Launch Report**\n")
    lines.append(f"**Score Breakdown**")
    lines.append(f"- Altitude: {int(peak_alt)}m → {alt_pts:,} pts")
    lines.append(f"- Time of Flight: {flight_time:.0f}s → {time_pts:,} pts")
    lines.append(f"- Payloads: {payload_count} → {pay_pts:,} pts")
    lines.append(f"**Total: {score_val:,} pts**\n")
    lines.append(f"**TOTAL: {score_val:,} pts**\n")
    lines.append(f"**Medal:** {medal_emoji} {medal_name}")
    lines.append(f"**Status:** {status_emoji} Burst: {burst}, Landed: {landed}, Crashed: {crashed}\n")
    lines.append(f"Gas: {gas_name} ({gas_mass:.3f}kg)")
    lines.append(f"Envelope: {env_name}")
    lines.append(f"Payload: {payload_name}")
    lines.append(f"Site: {site_name}\n")

    # Missions
    missions = summary.get("assigned_missions")
    if missions:
        lines.append(f"Missions: {', '.join(str(m) for m in missions)}\n")

    # Build timeline (limit entries to preserve header/status for Discord)
    lines.append("⏱ Altitude Timeline")
    timeline_entries = []
    for r in tel_list:
        v_dir = "↑" if r.get("vel", 0) > 0 else "↓"
        alt = r.get("altitude_m", r.get("alt", 0))
        t = r.get("time_s", r.get("time", 0))
        timeline_entries.append(f"  ⏱ {t:.0f}s  {alt:>8,.0f}m  {v_dir}")
    
    # Hard limit: keep first 5, last 5, and up to 10 evenly spaced middle entries
    if len(timeline_entries) > 20:
        kept = list(timeline_entries[:5])
        remaining = list(timeline_entries[5:-5])
        if remaining:
            step = max(1, len(remaining) // 10)
            for i in range(0, len(remaining), step):
                kept.append(remaining[i])
                if len(kept) >= 20:
                    break
        kept.extend(timeline_entries[-5:])
        timeline_entries = kept
    
    lines.extend(timeline_entries)

    result = "\n".join(lines)
    # Discord message cap — preserve header, truncate timeline if needed
    if len(result) > 2000:
        # Find where timeline starts so we can cut it cleanly
        timeline_start = result.find("⏱ Altitude Timeline")
        if timeline_start >= 0:
            # Keep everything before timeline + header, add abbreviated note
            result = result[:timeline_start]
            result += "\n...(truncated)\n"
        else:
            result = result[:1997] + "..."
    return result


def format_score_breakdown(score, peak_alt, payload_count, time_of_flight):
    """Format the score breakdown for the final result.

    Args:
        score: Total score (int/float)
        peak_alt: Peak altitude in meters
        payload_count: Number of payloads
        time_of_flight: Flight time in seconds
    """
    alt_pts = int(peak_alt * 1.0)
    time_pts = int(time_of_flight * 100.0)
    pay_pts = int(payload_count * 500.0)
    total = alt_pts + time_pts + pay_pts

    lines = []
    lines.append("**Score Breakdown**")
    lines.append(f"- Altitude: {peak_alt:.0f}m → {alt_pts:,} pts")
    lines.append(f"- Time: {time_of_flight:.0f}s → {time_pts:,} pts")
    lines.append(f"- Payloads: {payload_count} → {pay_pts:,} pts")
    lines.append(f"**TOTAL: {total:,} pts**")
    # Also output bare TOTAL for tests that check "TOTAL" in breakdown
    lines.append(f"**Total: {total:,} pts**")

    return "\n".join(lines)


def run_bot():
    token = os.environ.get("DISCORD_BF_TOKEN") or os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)