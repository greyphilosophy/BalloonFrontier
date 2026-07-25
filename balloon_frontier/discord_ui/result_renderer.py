"""Balloon Frontier — Discord result rendering.

Functions for formatting launch results, score breakdowns, and chart
output for Discord messages.
"""

import logging

from balloon_frontier.flight_score import calculate_flight_score
from balloon_frontier.medal_tier import get_medal_emoji, medal_tier_to_string
from balloon_frontier.ascii_chart import chart_to_string

logger = logging.getLogger(__name__)


def format_score_breakdown(score: float, peak_alt: float, payload_count: int, time_of_flight: float) -> str:
    """Format the score breakdown string."""
    alt_pts = int(peak_alt * 1.0)
    pay_pts = int(payload_count * 500.0)
    time_pts = int(time_of_flight * 100.0)
    lines = []
    lines.append(f"  Altitude: {alt_pts:,} pts")
    lines.append(f"  Payloads: {pay_pts:,} pts")
    lines.append(f"  Time: {time_pts:,} pts")
    lines.append(f"  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    lines.append(f"  TOTAL: {int(score):,} pts")
    return "\n".join(lines)


def make_result_embed(
    gas_name: str,
    gas_mass: float,
    env_name: str,
    payload_name: str,
    site_name: str,
    telemetry: list,
    summary: dict,
) -> str:
    """Build result embed for a launch.

    Args:
        gas_name: Display name of the gas type.
        gas_mass: Gas mass in kg.
        env_name: Envelope display name.
        payload_name: Payload display name.
        site_name: Launch site name.
        telemetry: List of telemetry dicts with time/alt/vel keys.
        summary: Dict with peak_altitude, burst, time_of_flight, etc.

    Returns:
        String content for the Discord message.
    """
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
    status = "\U0001f7e2" if peak >= target else "\U0001f7e1" if peak >= target * 0.7 else "\U0001f535"

    lines = ["\U0001f388 **Launch Report**\n"]
    lines.append(f"Gas: {gas_name} | Mass: {gas_mass}kg")
    lines.append(f"Envelope: {env_name}")
    lines.append(f"Site: {site_name}\n")

    missions = summary.get("assigned_missions")
    if missions:
        lines.append(f"Missions: {', '.join(missions)}\n")

    lines.append(f"Altitude: {status} {peak:,.0f}m / {target:,}m target")
    lines.append(f"Time of Flight: {time_of_flight:.1f}s")
    burst_text = "\U0001f4a5 Yes" if burst else "\U0001f7e2 No"
    lines.append(f"Burst: {burst_text}")
    lines.append(f"Medal: {medal_emoji} **{medal_name}**")
    lines.append("")

    # Score section
    lines.append("\U0001f3c6 **Score Breakdown**")
    lines.append(format_score_breakdown(score, peak, payload_count, time_of_flight))
    lines.append("")

    # Generate ASCII trajectory chart
    time_arr = [r["time"] for r in telemetry]
    alt_arr = [r["alt"] for r in telemetry]
    chart = chart_to_string(
        time_arr, alt_arr,
        title="\U0001f4c8 Flight Trajectory"
    )

    lines.append(chart + "\n")
    # Telemetry
    sampled = telemetry[::1]
    for r in sampled[:15]:
        v_dir = "\u2191" if r["vel"] > 0 else "\u2193"
        lines.append(f"\u23f1 {r['time']:.0f}s  {r['alt']:>8,.0f}m  {v_dir}")

    content = "\n".join(lines)
    return content
