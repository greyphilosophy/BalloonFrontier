"""Balloon Frontier — Launch handler.

Constructs ``LaunchRequest`` from Discord state, invokes
``FlightService.run()`` via ``asyncio.to_thread``, and formats the
result for Discord display.

Dependency injection: receives a ``FlightService`` instance rather than
importing the module-level singleton.
"""

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Optional

import discord

from balloon_frontier.flight_service import FlightService, FlightServiceError
from balloon_frontier.flight_score import calculate_flight_score
from balloon_frontier.launch_result import LaunchRequest, FillMode, MissionAssignment
from balloon_frontier.medal_tier import get_medal_emoji, medal_tier_to_string
from balloon_frontier.missions import load_mission_directory
from balloon_frontier.narrative_result import format_discord_results
from balloon_frontier.simulation import SimulationState, EnvelopeConfig, run_simulation as run_full_simulation
from balloon_frontier.discord_ui.result_renderer import make_result_embed, format_score_breakdown
from balloon_frontier.ascii_chart import chart_to_string

if TYPE_CHECKING:
    from balloon_frontier.discord_ui.configurator import BalloonConfigurator  # noqa: F401

logger = logging.getLogger(__name__)

# ─── Mission lazy-load guard ──────────────────────────────────────────
_missions_loaded = False


def _ensure_missions_loaded():
    """Lazily load missions so they are available for evaluation.

    Logs failures instead of silently swallowing them so that if the
    mission directory cannot be loaded the problem is visible in logs.
    Once attempted, it never retries (even on failure).
    """
    global _missions_loaded
    if _missions_loaded:
        return
    _missions_loaded = True
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        mission_dir = os.path.join(here, "..", "data", "missions")
        load_mission_directory(mission_dir)
    except Exception:
        logger.exception("Failed to load mission directory")


# ─── Simulation helper (retained for backward compat) ─────────────────

def run_simulation(
    gas_type,
    gas_mass,
    gas_temperature_k,
    payload_mass,
    drag_coeff,
    envelope_vol,
    stretch_ratio,
    envelope_mass_kg=1.0,
    *,
    mission_assignment=None,
    env_config=None,
    weather_impacts=None,
    has_pressure_valve=False,
    launch_altitude_m=0.0,
    wind_site_id="field",
):
    """Run fixed-step vertical simulation using the full physics engine.

    Preserves the original API so existing callers (and tests) work
    without modification.
    """
    _ensure_missions_loaded()

    if env_config is None:
        env_config = EnvelopeConfig(
            max_volume_m3=envelope_vol,
            burst_stretch_ratio=stretch_ratio,
            drag_coefficient=drag_coeff,
            mass_kg=envelope_mass_kg,
            contained_gas=True,
        )

    if weather_impacts:
        env_config.weather_burst_risk_modifier = weather_impacts.get("burst_risk", 1.0)
        env_config.weather_solar_modifier = weather_impacts.get("thermal_efficiency", 1.0)
        env_config.weather_pressure_modifier = weather_impacts.get("pressure_modifier", 1.0)
        env_config.weather_ascent_multiplier = weather_impacts.get("ascent_rate", 1.0)
        env_config.weather_drift_multiplier = weather_impacts.get("drift_factor", 1.0)

    state = SimulationState(
        gas_type=gas_type,
        gas_mass_kg=gas_mass,
        payload_mass_kg=payload_mass,
        envelope=env_config,
        altitude_m=launch_altitude_m,
        gas_temperature_k=gas_temperature_k,
        weather_ascent_multiplier=env_config.weather_ascent_multiplier if weather_impacts else 1.0,
        weather_drift_multiplier=env_config.weather_drift_multiplier if weather_impacts else 1.0,
        wind_enabled=True,
        wind_site_id=wind_site_id,
        ballast_mass_kg=0.0,
        has_pressure_valve=has_pressure_valve,
    )

    if mission_assignment:
        max_time = 43200.0
        max_steps = int(max_time / 0.1)
        tel_full = run_full_simulation(
            state, dt=0.1, total_time_s=max_time, max_steps=max_steps,
            step_interval=1.0,
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

    peak_alt = max(t["altitude_m"] for t in tel_full)
    burst = any(t.get("burst", False) for t in tel_full)
    landed = any(t.get("landed", False) for t in tel_full)
    crashed = any(t.get("crashed", False) for t in tel_full)

    telemetry = []
    for t in tel_full:
        telemetry.append({
            "time": t["time_s"],
            "alt": t["altitude_m"],
            "vel": t["velocity_mps"],
            "burst": t.get("burst", False),
            "landed": t.get("landed", False),
            "crashed": t.get("crashed", False),
        })

    flight_time = tel_full[-1]["time_s"]
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


# ─── Launch handler (DI-wired) ───────────────────────────────────────

async def run_launch(
    configurator: "BalloonConfigurator",
    interaction: discord.Interaction,
    service: FlightService,
):
    """Handle the launch button press and return the current outcome.

    Returns ``None`` when the launch or rendering fails, allowing callers to
    base follow-up UI on this attempt rather than historical player state.
    """
    await interaction.response.defer(thinking=True, ephemeral=False)

    try:
        player_id = (
            str(interaction.user.id)
            if hasattr(interaction, "user") and interaction.user
            else "anonymous"
        )

        state = configurator.state
        from balloon_frontier.discord_ui.configurator import (
            GAS_OPTIONS, ENVELOPE_OPTIONS, SITE_OPTIONS, PAYLOAD_OPTIONS,
        )

        gas_info = GAS_OPTIONS[state["gas"]]
        env_info = ENVELOPE_OPTIONS[state["envelope"]]
        site_info = SITE_OPTIONS[state["site"]]
        payloads = [PAYLOAD_OPTIONS[p] for p in state["payloads"]]
        payload_names = [p[0] for p in payloads]

        gas_mass = configurator.state.get("gas_mass")
        if gas_mass is None:
            gas_mass = configurator._compute_gas_mass()
            configurator.state["gas_mass"] = gas_mass

        fill_mode = FillMode(configurator.state.get("fill_mode", "auto"))
        manual_mass = configurator.state.get("manual_gas_mass")

        launch_request = LaunchRequest(
            gas_id=state["gas"],
            envelope_id=state["envelope"],
            payload_ids=tuple(state.get("payloads") or []),
            launch_site_id=state["site"],
            fill_mode=fill_mode,
            manual_gas_mass_kg=manual_mass,
            player_id=player_id,
            balloon_size=None,
        )

        try:
            result = await asyncio.to_thread(service.run, launch_request)
        except FlightServiceError:
            logger.exception("Flight service failed")
            await interaction.edit_original_response(
                content="❌ The launch simulation failed. Please try again.",
                view=None,
            )
            return None

        result_obj = result.result
        tel = [
            {
                "time": tp.time_s,
                "alt": tp.altitude_m,
                "vel": tp.velocity_mps,
                "burst": tp.burst,
                "landed": tp.landed,
                "crashed": tp.crashed,
            }
            for tp in result_obj.telemetry
        ]

        peak_alt = result_obj.peak_altitude_m
        time_of_flight = result_obj.duration_s
        burst = result_obj.burst
        landed = result_obj.landed
        crashed = result_obj.crashed
        mission_results = result.mission_results

        payload_keys = list(state.get("payloads") or [])
        payload_display = ", ".join(payload_names)
        if payload_keys == ["none"]:
            payload_display = "None"

        chart_str = chart_to_string(
            [r["time"] for r in tel],
            [r["alt"] for r in tel],
            title="📈 Flight Trajectory",
        )

        weather_dict = {
            "name": result.weather.name if result.weather else "",
            "description": result.weather.description if result.weather else "",
            "severity": result.weather.severity if result.weather else "",
            "flight_modifier": result.weather.flight_modifier if result.weather else "",
        }
        mission_assignment = result.mission_assignment
        if isinstance(mission_assignment, dict):
            mission_assignment_dict = mission_assignment
        else:
            mission_assignment_dict = {
                "mission_ids": list(mission_assignment.mission_ids) if mission_assignment else [],
                "seed": mission_assignment.seed if mission_assignment else None,
                "missions": list(mission_assignment.mission_ids) if mission_assignment else [],
                "mission_count": mission_assignment.mission_count if mission_assignment else 0,
            }

        result_content = format_discord_results(
            peak_altitude=peak_alt,
            burst=burst,
            landed=landed,
            crashed=crashed,
            time_of_flight=time_of_flight,
            telemetry=tel,
            gas_name=gas_info[0],
            gas_mass=launch_request.gas_mass_kg,
            env_name=env_info[0],
            payload_names=payload_display,
            site_name=site_info.name,
            mission_assignment=mission_assignment_dict,
            player_id=player_id,
            weather_event=weather_dict,
            chart_str=chart_str,
        )

        if mission_results:
            mission_lines = ["\n🎯 **Mission Results:**"]
            for mr in mission_results:
                status = "✅" if mr.completed else "❌"
                reward_str = f" (+{mr.reward} credits)" if mr.reward else ""
                mission_lines.append(
                    f"  {status} {mr.mission_id}{reward_str}: {mr.explanation}"
                )
            mission_text = "\n".join(mission_lines)
            if chart_str:
                result_content = result_content.replace(
                    "\n" + chart_str,
                    mission_text + "\n" + chart_str,
                )
            else:
                result_content += mission_text

        if len(result_content) > 2000:
            result_content = result_content[:1997] + "..."
        await interaction.edit_original_response(content=result_content, view=None)
        return result
    except Exception:
        logger.exception("Balloon launch failed")
        await interaction.edit_original_response(
            content="❌ The launch simulation failed. Please try again.",
            view=None,
        )
        return None
