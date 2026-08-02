"""Keep tutorial debriefs evidence-based and Discord reports valid."""

from __future__ import annotations

from dataclasses import replace
from functools import wraps

_UNMODELED_CONTROL_NOTE = (
    "The simulation ended while the aircraft was still airborne. The current "
    "model does not yet simulate quadcopter battery endurance, radio range, or "
    "active steering authority, so it cannot identify a specific control failure."
)
_RECOVERY_TRADEOFF_NOTE = (
    "The selected configuration has design tradeoffs, but the telemetry does "
    "not prove which one prevented recovery."
)


def _unresolved(result) -> bool:
    return not any(
        bool(getattr(result, field, False))
        for field in ("burst", "landed", "crashed")
    )


def _clarify_unresolved_quadcopter_outcome(original):
    @wraps(original)
    def evaluate(request, outcome):
        evaluated = original(request, outcome)
        result = outcome.result
        if not _unresolved(result) or "quadcopter" not in set(request.payload_ids):
            return evaluated

        rewritten = []
        for mission in evaluated.mission_results:
            if mission.mission_id != "first_flight":
                rewritten.append(mission)
                continue

            explanation = mission.explanation.replace(
                "The aircraft completed the endurance course under control.",
                "The aircraft did not complete a confirmed recovery.",
            ).replace(
                "The aircraft did not complete the endurance course safely.",
                "The aircraft did not complete a confirmed recovery.",
            ).replace(
                "No landing was confirmed before the simulation ended.",
                "The simulation ended while the aircraft was still airborne.",
            )

            why_marker = "\n**Why**\n- "
            try_marker = "\n**Try next**\n- "
            if why_marker in explanation and try_marker in explanation:
                before, remainder = explanation.split(why_marker, 1)
                _old_why, after = remainder.split(try_marker, 1)
                explanation = (
                    before
                    + why_marker
                    + _UNMODELED_CONTROL_NOTE
                    + "\n- "
                    + _RECOVERY_TRADEOFF_NOTE
                    + try_marker
                    + after
                )

            rewritten.append(
                replace(
                    mission,
                    completed=False,
                    reward=0,
                    explanation=explanation,
                )
            )
        return replace(evaluated, mission_results=tuple(rewritten))

    evaluate._balloon_frontier_evidence_based_debrief = True
    return evaluate


def _fenced_chart(original):
    @wraps(original)
    def render(*args, **kwargs):
        chart = original(*args, **kwargs)
        if not chart or chart.startswith("```"):
            return chart
        return f"```text\n{chart}\n```"

    render._balloon_frontier_discord_fenced = True
    return render


def _replace_unresolved_descent_narrative(original):
    @wraps(original)
    def render(*args, **kwargs):
        report = original(*args, **kwargs)
        telemetry = kwargs.get("telemetry")
        if telemetry is None and len(args) >= 6:
            telemetry = args[5]
        points = list(telemetry or ())
        if not points:
            return report

        landed = bool(kwargs.get("landed", args[2] if len(args) > 2 else False))
        crashed = bool(kwargs.get("crashed", args[3] if len(args) > 3 else False))
        burst = bool(kwargs.get("burst", args[1] if len(args) > 1 else False))
        if landed or crashed or burst:
            return report

        def value(point, key, fallback):
            if isinstance(point, dict):
                return point.get(key, point.get(fallback, 0.0))
            return getattr(point, key, getattr(point, fallback, 0.0))

        altitudes = [float(value(point, "altitude_m", "alt")) for point in points]
        final_velocity = float(value(points[-1], "velocity_mps", "vel"))
        passed_apogee = altitudes[-1] < max(altitudes) - 1.0 and final_velocity < 0.0
        if not passed_apogee:
            return report

        heading = "📈 **Still climbing slowly...**"
        if heading not in report:
            return report
        lines = report.splitlines()
        index = lines.index(heading)
        end = index + 1
        while end < len(lines) and lines[end].startswith("  "):
            end += 1
        lines[index:end] = [
            "🛰️ **Recovery not completed**",
            "  The aircraft passed peak altitude and was descending when the simulation ended.",
        ]
        return "\n".join(lines)

    render._balloon_frontier_unresolved_descent = True
    return render


def _safe_discord_content(content: str, limit: int = 2000) -> str:
    """Keep content within Discord limits without leaving an open code fence."""
    text = str(content)
    if len(text) <= limit and text.count("```") % 2 == 0:
        return text

    if text.count("```") % 2:
        opening = text.rfind("```")
        if opening >= 0:
            suffix = "\n*Trajectory omitted because the report reached Discord's message limit.*"
            return (text[:opening].rstrip() + suffix)[:limit]

    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    if text.count("```") % 2:
        opening = text.rfind("```")
        text = text[:opening].rstrip()
    return text[:limit]


def _safe_send_results(original):
    @wraps(original)
    async def send(interaction, content: str):
        return await original(interaction, _safe_discord_content(content))

    send._balloon_frontier_balanced_content = True
    return send


def _safe_edit_results(original):
    @wraps(original)
    async def edit(interaction, content: str, continue_view):
        return await original(
            interaction,
            _safe_discord_content(content),
            continue_view,
        )

    edit._balloon_frontier_balanced_content = True
    return edit


def install_tutorial_report_guard() -> None:
    """Install report corrections exactly once."""
    from balloon_frontier import tutorial
    from balloon_frontier.discord_ui import launch_handler

    if not getattr(
        tutorial.evaluate_tutorial_outcome,
        "_balloon_frontier_evidence_based_debrief",
        False,
    ):
        tutorial.evaluate_tutorial_outcome = _clarify_unresolved_quadcopter_outcome(
            tutorial.evaluate_tutorial_outcome
        )

    if not getattr(
        launch_handler.chart_to_string,
        "_balloon_frontier_discord_fenced",
        False,
    ):
        launch_handler.chart_to_string = _fenced_chart(launch_handler.chart_to_string)

    if not getattr(
        launch_handler.format_discord_results,
        "_balloon_frontier_unresolved_descent",
        False,
    ):
        launch_handler.format_discord_results = _replace_unresolved_descent_narrative(
            launch_handler.format_discord_results
        )

    if not getattr(
        launch_handler._send_results,
        "_balloon_frontier_balanced_content",
        False,
    ):
        launch_handler._send_results = _safe_send_results(
            launch_handler._send_results
        )

    if not getattr(
        launch_handler._edit_results_with_optional_view,
        "_balloon_frontier_balanced_content",
        False,
    ):
        launch_handler._edit_results_with_optional_view = _safe_edit_results(
            launch_handler._edit_results_with_optional_view
        )
