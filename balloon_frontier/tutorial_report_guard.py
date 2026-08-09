"""Keep Discord launch reports valid without changing simulation behavior.

The module name is retained for compatibility with older imports. It contains
presentation-only guards: code-fenced charts, evidence-based descent wording,
and Discord-safe message limits.
"""

from __future__ import annotations

from functools import wraps


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
    text = str(content)
    if len(text) <= limit and text.count("```") % 2 == 0:
        return text
    if text.count("```") % 2:
        opening = text.rfind("```")
        if opening >= 0:
            suffix = "\n*Trajectory omitted because the report reached Discord's message limit.*"
            available = max(0, limit - len(suffix))
            return text[:opening].rstrip()[:available] + suffix
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    if text.count("```") % 2:
        text = text[: text.rfind("```")].rstrip()
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
        return await original(interaction, _safe_discord_content(content), continue_view)

    edit._balloon_frontier_balanced_content = True
    return edit


def install_tutorial_report_guard() -> None:
    """Install presentation-only Discord report guards.

    The legacy function name is kept so older imports do not break.
    """
    from balloon_frontier.discord_ui import launch_handler

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
        launch_handler._send_results = _safe_send_results(launch_handler._send_results)

    if not getattr(
        launch_handler._edit_results_with_optional_view,
        "_balloon_frontier_balanced_content",
        False,
    ):
        launch_handler._edit_results_with_optional_view = _safe_edit_results(
            launch_handler._edit_results_with_optional_view
        )
