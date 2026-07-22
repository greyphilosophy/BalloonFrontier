"""Balloon Frontier — Narrative Flight Result Generation.

Generates narrative framing for flight results based on mission evaluation,
progression state, and actual flight outcomes. Connects the simulation results
back into the game's story and progression systems.

This module:
  - Evaluates flights against mission objectives
  - Updates player progression (reputation, budget, unlocks)
  - Generates narrative flavor text for results
  - Formats results for Discord display

Reference: GDD Sections 14.2, 17, 20, 21.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .missions import get_mission, MISSIONS
from .evaluation import evaluate_flight, format_mission_result
from .progression import PlayerRegistry, ENVELOPES


def evaluate_and_update_progression(
    telemetry: List[dict],
    mission_ids: List[str],
    payloads: List[str],
    player_id: str,
    budget_reward: int = 100,
) -> Dict:
    """Evaluate flight against missions and update player progression.

    This is the central function that connects simulation results to the game's
    progression system. It:
    1. Evaluates each mission against the flight telemetry
    2. Aggregates scores across all missions
    3. Updates the player's reputation, budget, and unlocks
    4. Returns the complete evaluation result

    Args:
        telemetry: Flight telemetry from the simulation.
        mission_ids: List of mission IDs assigned to this flight.
        payloads: List of payload identifiers used.
        player_id: Discord user ID or player identifier.
        budget_reward: Base budget reward for successful mission completion.

    Returns:
        Dict with keys:
            - missions: list of individual mission result dicts
            - overall_score: weighted average score (0-100)
            - overall_success: bool — True if overall_score >= 60
            - reputation_gained: int
            - budget_earned: int
            - new_unlocks: list of envelope names unlocked
            - player_state: current PlayerState
    """
    player = PlayerRegistry.get_or_create(player_id)
    all_mission_results = []
    total_weighted_score = 0.0
    total_weight = 0.0
    total_rep_gain = 0
    total_budget_earned = 0
    new_unlocks = []

    for mission_id in mission_ids:
        if mission_id not in MISSIONS:
            continue

        mission = get_mission(mission_id)
        mission_config = {
            "id": mission.id,
            "objectives": [
                {"type": o.type, "params": o.params, "weight": 1.0}
                for o in mission.objectives
            ],
        }

        result = evaluate_flight(telemetry, mission_config, payloads)
        score = result.score

        all_mission_results.append({
            "mission_id": mission.id,
            "title": mission.title,
            "score": round(score, 1),
            "is_success": result.is_success,
            "notes": result.notes,
            "objectives_scores": [
                {"type": o.type, "score": round(o.actual_value, 1) if isinstance(o.actual_value, (int, float)) else 0, "description": o.type}
                for o in result.objectives
            ],
        })

        # Aggregate scores
        total_weighted_score += score * 1.0
        total_weight += 1.0

        # Update player progression
        mission_result = {
            "id": mission.id,
            "objectives": [
                {"type": o.type, "params": o.params, "weight": 1.0}
                for o in mission.objectives
            ],
        }
        eval_result = evaluate_flight(telemetry, mission_result, payloads)
        rep_gain = min(int(eval_result.score / 33), 2)
        budget_earned = int(budget_reward * eval_result.score / 100)
        total_rep_gain += rep_gain
        total_budget_earned += budget_earned

        player.reputation += rep_gain
        player.budget += budget_earned
        player.total_flights += 1
        if eval_result.is_success:
            player.successful_flights += 1
        if mission_id not in player.missions_completed:
            player.missions_completed.append(mission_id)

        # Check envelope unlocks
        for env in ENVELOPES:
            if env.id not in player.unlocked_envelopes:
                if player.reputation >= env.min_reputation and player.budget >= env.cost:
                    player.unlocked_envelopes.append(env.id)
                    new_unlocks.append(env.name)

    # Save state
    try:
        player.save()
    except Exception:
        pass

    overall_score = (total_weighted_score / total_weight) if total_weight > 0 else 0
    overall_success = overall_score >= 60

    return {
        "missions": all_mission_results,
        "overall_score": round(overall_score, 1),
        "overall_success": overall_success,
        "reputation_gained": total_rep_gain,
        "budget_earned": total_budget_earned,
        "new_unlocks": new_unlocks,
        "player_state": {
            "reputation": player.reputation,
            "budget": player.budget,
            "unlocked_envelopes": player.unlocked_envelopes[:],
            "total_flights": player.total_flights,
            "successful_flights": player.successful_flights,
        },
    }


def generate_narrative_summary(
    peak_altitude: float,
    burst: bool,
    landed: bool,
    crashed: bool,
    time_of_flight: float,
    mission_result: Optional[Dict] = None,
    weather_briefing: Optional[str] = None,
) -> str:
    """Generate narrative flavor text based on flight outcome.

    Args:
        peak_altitude: Maximum altitude reached in meters.
        burst: Whether the balloon burst.
        landed: Whether the balloon landed safely.
        crashed: Whether the balloon crashed.
        time_of_flight: Total flight time in seconds.
        mission_result: Optional mission evaluation result dict.
        weather_briefing: Optional weather briefing text.

    Returns:
        Multi-line narrative text for display in results.
    """
    lines = []
    target = 30000

    # ── Weather context ──
    if weather_briefing:
        lines.append(f"{weather_briefing}\n")

    # ── Flight outcome narrative ──
    if burst:
        lines.append("💥 **Your balloon burst!**")
        if peak_altitude < target * 0.5:
            lines.append("  The envelope couldn't handle the pressure at lower altitude. Try a larger balloon or lighter gas fill next time.")
        elif peak_altitude < target:
            lines.append(f"  You got close to {target:,}m, but the expanding gas at high altitude was too much. A mylar or zero-pressure envelope might help.")
        else:
            lines.append(f"  You reached {peak_altitude:,.0f}m — incredibly high! The burst was just a few thousand meters too late.")

    elif crashed:
        lines.append("🏁 **Crash landing!**")
        if time_of_flight < 60:
            lines.append("  The balloon descended rapidly — possibly due to payload weight or gas permeability.")
        else:
            lines.append(f"  After {time_of_flight:.0f}s of flight, the balloon made an uncontrolled descent. Check your parachutes!")

    elif landed:
        lines.append("🏁 **Safe landing!**")
        lines.append(f"  The balloon descended gently after {time_of_flight:.0f}s of flight. All payloads recovered.")

    else:
        # Still climbing after simulation ended
        if peak_altitude < target * 0.3:
            lines.append("📈 **Still climbing slowly...**")
            lines.append("  Your balloon is gaining altitude but not fast enough. Try heavier gas fill or lighter payloads.")
        elif peak_altitude < target * 0.7:
            lines.append("📈 **Gaining altitude!**")
            lines.append(f"  You've reached {peak_altitude:,.0f}m and the ascent continues. More time and a larger balloon could get you to {target:,}m.")
        else:
            lines.append("🚀 **Impressive climb!**")
            lines.append(f"  {peak_altitude:,.0f}m and still going! You're very close to the {target:,}m target.")

    # ── Mission context ──
    if mission_result:
        lines.append("")
        if mission_result.get("missions"):
            for m in mission_result["missions"]:
                icon = "✅" if m["is_success"] else "❌"
                lines.append(f"  {icon} **{m['title']}**: {m['score']:.0f}/100")
                if m.get("notes"):
                    lines.append(f"     📝 {m['notes']}")

            lines.append("")
            lines.append(f"  **Overall Score: {mission_result.get('overall_score', 0):.1f}/100**")
            lines.append(f"  {'🎉 Mission Success!' if mission_result.get('overall_success') else '⚠️ Mission Failed — Try Again!'}")

            lines.append("")
            lines.append(f"  📈 Reputation: +{mission_result.get('reputation_gained', 0)} (Total: {mission_result.get('player_state', {}).get('reputation', 0)})")
            lines.append(f"  💰 Budget: +{mission_result.get('budget_earned', 0)} (Total: {mission_result.get('player_state', {}).get('budget', 0)})")

            if mission_result.get("new_unlocks"):
                for unlock in mission_result["new_unlocks"]:
                    lines.append(f"  🔓 **New envelope unlocked: {unlock}!**")
            else:
                state = mission_result.get("player_state", {})
                if state:
                    rep_needed = 0
                    budget_needed = 0
                    for env in ENVELOPES:
                        if env.id not in state.get("unlocked_envelopes", []):
                            if rep_needed < env.min_reputation:
                                rep_needed = env.min_reputation
                            if budget_needed < env.cost:
                                budget_needed = env.cost
                    if rep_needed > state.get("reputation", 0):
                        lines.append(f"  🔒 Next unlock: {rep_needed - state.get('reputation', 0)} more reputation needed")
                    if budget_needed > state.get("budget", 0):
                        lines.append(f"  🔒 Next unlock: {budget_needed - state.get('budget', 0)} more budget needed")

    return "\n".join(lines)


def format_discord_results(
    peak_altitude: float,
    burst: bool,
    landed: bool,
    crashed: bool,
    time_of_flight: float,
    telemetry: List[dict],
    gas_name: str,
    gas_mass: float,
    env_name: str,
    payload_names: str,
    site_name: str,
    mission_assignment: Optional[Dict] = None,
    player_id: str = "unknown",
    weather_event: Optional[Dict] = None,
    chart_str: str = "",
) -> str:
    """Format a complete Discord result message with narrative framing.

    This is the main entry point for generating launch results in Discord.
    It connects simulation data → mission evaluation → progression → narrative.

    Args:
        peak_altitude: Maximum altitude reached.
        burst: Whether balloon burst.
        landed: Whether balloon landed safely.
        crashed: Whether balloon crashed.
        time_of_flight: Total flight time.
        telemetry: Flight telemetry data.
        gas_name: Display name of gas type.
        gas_mass: Gas mass in kg.
        env_name: Display name of envelope type.
        payload_names: Comma-separated payload names.
        site_name: Launch site name.
        mission_assignment: Mission assignment dict from mission system.
        player_id: Player identifier for progression tracking.
        weather_event: Weather event for this launch (if generated).
        chart_str: ASCII trajectory chart (pre-generated).

    Returns:
        Formatted result string for Discord (under 2000 chars after truncation).
    """
    lines = ["🎈 **Launch Report**\n"]
    lines.append(f"Gas: {gas_name} | Mass: {gas_mass:.3f}kg")
    lines.append(f"Envelope: {env_name}")
    lines.append(f"Payloads: {payload_names}")
    lines.append(f"Site: {site_name}\n")

    # Weather briefing
    if weather_event:
        if weather_event.get("name"):
            lines.append(f"{weather_event['name']}")
        if weather_event.get("description"):
            lines.append(weather_event["description"])
        lines.append(f"{weather_event.get('severity', '')} — {weather_event.get('flight_modifier', '')}\n")

    # Mission evaluation
    mission_result = None
    if mission_assignment and mission_assignment.get("missions"):
        mission_ids = mission_assignment["missions"]
        payload_list = payload_names.lower().split(",") if payload_names else ["none"]

        mission_result = evaluate_and_update_progression(
            telemetry=telemetry,
            mission_ids=mission_ids,
            payloads=payload_list,
            player_id=player_id,
        )

    # Narrative summary
    lines.append(generate_narrative_summary(
        peak_altitude=peak_altitude,
        burst=burst,
        landed=landed,
        crashed=crashed,
        time_of_flight=time_of_flight,
        mission_result=mission_result,
        weather_briefing=None,
    ))

    # Trajectory chart
    if chart_str:
        lines.append(f"\n{chart_str}")

    return "\n".join(lines)