"""Discord launch execution, ANSI playback, and result delivery."""

import asyncio
import logging
import os
from typing import TYPE_CHECKING

import discord

from balloon_frontier.ascii_chart import chart_to_string
from balloon_frontier.discord_ui.animator import DiscordFlightAnimator
from balloon_frontier.flight_score import calculate_flight_score
from balloon_frontier.flight_service import FlightService
from balloon_frontier.launch_result import FillMode, LaunchRequest
from balloon_frontier.medal_tier import get_medal_emoji, medal_tier_to_string
from balloon_frontier.missions import load_mission_directory
from balloon_frontier.narrative_result import format_discord_results
from balloon_frontier.presentation import build_flight_moments
from balloon_frontier.simulation import (
    EnvelopeConfig,
    SimulationState,
    run_simulation as run_full_simulation,
)

if TYPE_CHECKING:
    from balloon_frontier.discord_ui.configurator import BalloonConfigurator

logger = logging.getLogger(__name__)
_missions_loaded = False


def _ensure_missions_loaded():
    global _missions_loaded
    if _missions_loaded:
        return
    _missions_loaded = True
    try:
        mission_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "data",
            "missions",
        )
        load_mission_directory(mission_dir)
    except Exception:
        logger.exception("Failed to load mission directory")


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
    """Backward-compatible fixed-step simulation helper."""
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
        env_config.weather_burst_risk_modifier = weather_impacts.get(
            "burst_risk", 1.0
        )
        env_config.weather_solar_modifier = weather_impacts.get(
            "thermal_efficiency", 1.0
        )
        env_config.weather_pressure_modifier = weather_impacts.get(
            "pressure_modifier", 1.0
        )
        env_config.weather_ascent_multiplier = weather_impacts.get(
            "ascent_rate", 1.0
        )
        env_config.weather_drift_multiplier = weather_impacts.get(
            "drift_factor", 1.0
        )
    state = SimulationState(
        gas_type=gas_type,
        gas_mass_kg=gas_mass,
        payload_mass_kg=payload_mass,
        envelope=env_config,
        altitude_m=launch_altitude_m,
        gas_temperature_k=gas_temperature_k,
        weather_ascent_multiplier=(
            env_config.weather_ascent_multiplier if weather_impacts else 1.0
        ),
        weather_drift_multiplier=(
            env_config.weather_drift_multiplier if weather_impacts else 1.0
        ),
        wind_enabled=True,
        wind_site_id=wind_site_id,
        ballast_mass_kg=0.0,
        has_pressure_valve=has_pressure_valve,
    )
    if mission_assignment:
        max_time = 43200.0
        tel_full = run_full_simulation(
            state,
            dt=0.1,
            total_time_s=max_time,
            max_steps=int(max_time / 0.1),
            step_interval=1.0,
        )
    else:
        tel_full = run_full_simulation(
            state,
            dt=0.1,
            total_time_s=150.0,
            max_steps=10000,
        )
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
    telemetry = [
        {
            "time": t["time_s"],
            "alt": t["altitude_m"],
            "vel": t["velocity_mps"],
            "burst": t.get("burst", False),
            "landed": t.get("landed", False),
            "crashed": t.get("crashed", False),
        }
        for t in tel_full
    ]
    flight_time = tel_full[-1]["time_s"]
    summary = {
        "peak_altitude": peak_alt,
        "burst": any(t.get("burst", False) for t in tel_full),
        "landed": any(t.get("landed", False) for t in tel_full),
        "crashed": any(t.get("crashed", False) for t in tel_full),
        "time_of_flight": flight_time,
        "payload_count": 1,
        "score": calculate_flight_score(peak_alt, 1, flight_time),
        "medal": medal_tier_to_string(peak_alt),
        "medal_emoji": get_medal_emoji(peak_alt),
    }
    if mission_assignment:
        summary.update(
            assigned_missions=list(mission_assignment.get("missions", [])),
            mission_seed=mission_assignment.get("seed"),
            mission_count=mission_assignment.get("mission_count"),
        )
    return telemetry, summary


def _tutorial_continue_view(configurator, interaction, result):
    context = getattr(configurator, "_game_entry_context", None)
    if not context:
        return None

    from balloon_frontier.game_modes import GameMode

    if context.get("mode") is not GameMode.TUTORIAL:
        return None
    completed = any(
        mission.mission_id == "first_flight" and mission.completed
        for mission in result.mission_results
    )
    if not completed:
        return None

    from balloon_frontier.discord_ui.game_menu import ContinueToStoryView

    kwargs = {
        "player_id": str(interaction.user.id),
        "channel_kind": context["channel_kind"],
        "service": context["service"],
        "on_finished": context.get("on_finished"),
    }
    on_view_changed = context.get("on_view_changed")
    if on_view_changed is not None:
        kwargs["on_view_changed"] = on_view_changed

    view = ContinueToStoryView(**kwargs)
    setattr(configurator, "_tutorial_continuation_handled", True)
    if on_view_changed is not None:
        try:
            on_view_changed(view)
        except Exception:
            logger.exception("Failed to register tutorial continuation view")
    return view


async def _send_results(interaction, content: str) -> bool:
    """Send results as a follow-up when supported."""
    followup = getattr(interaction, "followup", None)
    if followup is not None and hasattr(followup, "send"):
        await followup.send(content=content)
        return True
    return False


async def _safe_edit_original_response(interaction, **kwargs) -> bool:
    """Best-effort terminal edit that never creates a second callback failure."""
    try:
        await interaction.edit_original_response(**kwargs)
    except Exception:
        logger.exception("Discord rejected terminal launch status update")
        return False
    return True


async def _attach_tutorial_continue_view(interaction, continue_view) -> bool:
    """Attach optional tutorial controls without invalidating a completed flight."""
    if continue_view is None:
        return False
    try:
        await interaction.edit_original_response(view=continue_view)
    except Exception:
        logger.warning(
            "Tutorial completed, but continuation controls could not be attached",
            exc_info=True,
        )
        return False
    return True


async def _edit_results_with_optional_view(
    interaction,
    content: str,
    continue_view,
) -> None:
    """Render results, retrying without optional controls if Discord rejects them."""
    try:
        await interaction.edit_original_response(
            content=content,
            view=continue_view,
        )
    except Exception:
        if continue_view is None:
            raise
        logger.warning(
            "Tutorial results rendered, but continuation controls were rejected",
            exc_info=True,
        )
        await interaction.edit_original_response(content=content, view=None)


def _limit_result_content(configurator, content: str, limit: int = 2000) -> str:
    """Keep legacy single-message limits unless a split delivery owns the result."""
    text = str(content)
    if len(text) <= limit:
        return text
    if getattr(configurator, "_balloon_frontier_split_result_delivery", False):
        return text
    return text[: limit - 3] + "..."


async def run_launch(
    configurator: "BalloonConfigurator",
    interaction: discord.Interaction,
    service: FlightService,
):
    await interaction.response.defer(thinking=True, ephemeral=False)
    simulation_completed = False
    try:
        player_id = (
            str(interaction.user.id)
            if getattr(interaction, "user", None)
            else "anonymous"
        )
        state = configurator.state
        from balloon_frontier.discord_ui.configurator import (
            ENVELOPE_OPTIONS,
            GAS_OPTIONS,
            PAYLOAD_OPTIONS,
            SITE_OPTIONS,
        )

        gas_info = GAS_OPTIONS[state["gas"]]
        env_info = ENVELOPE_OPTIONS[state["envelope"]]
        site_info = SITE_OPTIONS[state["site"]]
        payloads = [PAYLOAD_OPTIONS[p] for p in state["payloads"]]
        payload_names = [p[0] for p in payloads]
        gas_mass = state.get("gas_mass")
        if gas_mass is None:
            gas_mass = configurator._compute_gas_mass()
            state["gas_mass"] = gas_mass
        launch_request = LaunchRequest(
            gas_id=state["gas"],
            envelope_id=state["envelope"],
            payload_ids=tuple(state.get("payloads") or []),
            launch_site_id=state["site"],
            fill_mode=FillMode(state.get("fill_mode", "auto")),
            manual_gas_mass_kg=state.get("manual_gas_mass"),
            player_id=player_id,
            balloon_size=None,
        )
        try:
            result = await asyncio.to_thread(service.run, launch_request)
        except Exception:
            logger.exception("Flight service failed")
            await _safe_edit_original_response(
                interaction,
                content="❌ The launch simulation failed. Please try again.",
                view=None,
            )
            return None
        simulation_completed = True

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
        payload_display = (
            "None"
            if list(state.get("payloads") or []) == ["none"]
            else ", ".join(payload_names)
        )
        chart_str = chart_to_string(
            [r["time"] for r in tel],
            [r["alt"] for r in tel],
            title="📈 Flight Trajectory",
        )
        weather = result.weather
        weather_dict = {
            "name": weather.name if weather else "",
            "description": weather.description if weather else "",
            "severity": weather.severity if weather else "",
            "flight_modifier": weather.flight_modifier if weather else "",
        }
        assignment = result.mission_assignment
        assignment_dict = (
            assignment
            if isinstance(assignment, dict)
            else {
                "mission_ids": list(assignment.mission_ids) if assignment else [],
                "seed": assignment.seed if assignment else None,
                "missions": list(assignment.mission_ids) if assignment else [],
                "mission_count": assignment.mission_count if assignment else 0,
            }
        )
        result_content = format_discord_results(
            peak_altitude=result_obj.peak_altitude_m,
            burst=result_obj.burst,
            landed=result_obj.landed,
            crashed=result_obj.crashed,
            time_of_flight=result_obj.duration_s,
            telemetry=tel,
            gas_name=gas_info[0],
            gas_mass=launch_request.gas_mass_kg,
            env_name=env_info[0],
            payload_names=payload_display,
            site_name=site_info.name,
            mission_assignment=assignment_dict,
            player_id=player_id,
            weather_event=weather_dict,
            chart_str=chart_str,
        )
        if result.mission_results:
            lines = ["\n🎯 **Mission Results:**"]
            for mr in result.mission_results:
                reward = f" (+{mr.reward} credits)" if mr.reward else ""
                lines.append(
                    f"  {'✅' if mr.completed else '❌'} "
                    f"{mr.mission_id}{reward}: {mr.explanation}"
                )
            mission_text = "\n".join(lines)
            result_content = (
                result_content.replace(
                    "\n" + chart_str,
                    mission_text + "\n" + chart_str,
                )
                if chart_str
                else result_content + mission_text
            )
        result_content = _limit_result_content(configurator, result_content)

        try:
            continue_view = _tutorial_continue_view(
                configurator,
                interaction,
                result,
            )
        except Exception:
            logger.exception("Failed to build tutorial continuation controls")
            continue_view = None

        followup = getattr(interaction, "followup", None)
        supports_followup = followup is not None and hasattr(followup, "send")

        if supports_followup:
            moments = build_flight_moments(
                result_obj.telemetry,
                max_frames=7,
            )
            try:
                await DiscordFlightAnimator(duration_s=3.5).play(
                    interaction,
                    moments,
                )
            except (discord.HTTPException, ValueError):
                logger.warning(
                    "Discord flight animation interrupted",
                    exc_info=True,
                )
            await _send_results(interaction, result_content)
            await _attach_tutorial_continue_view(interaction, continue_view)
        else:
            await _edit_results_with_optional_view(
                interaction,
                result_content,
                continue_view,
            )
        return result
    except Exception:
        if simulation_completed:
            logger.exception("Balloon launch result delivery failed")
            content = (
                "⚠️ The flight completed, but its results could not be displayed. "
                "Please try `/play` to continue."
            )
        else:
            logger.exception("Balloon launch setup failed")
            content = "❌ The launch simulation failed. Please try again."
        await _safe_edit_original_response(
            interaction,
            content=content,
            view=None,
        )
        return None
