"""Keep tutorial debriefs evidence-based and Discord charts aligned."""

from __future__ import annotations

from dataclasses import replace
from functools import wraps


_UNMODELED_CONTROL_NOTE = (
    "The simulation ended while the aircraft was still airborne. The current "
    "model does not yet simulate quadcopter battery endurance, radio range, or "
    "active steering authority, so it cannot identify a specific control failure."
)


def _clarify_unresolved_quadcopter_outcome(original):
    @wraps(original)
    def evaluate(request, outcome):
        evaluated = original(request, outcome)
        result = outcome.result
        unresolved = not any(
            bool(getattr(result, field, False))
            for field in ("burst", "landed", "crashed")
        )
        if not unresolved or "quadcopter" not in set(request.payload_ids):
            return evaluated

        rewritten = []
        for mission in evaluated.mission_results:
            if mission.mission_id != "first_flight" or mission.completed:
                rewritten.append(mission)
                continue

            explanation = mission.explanation
            why_marker = "\n**Why**\n- "
            try_marker = "\n**Try next**\n- "
            if why_marker in explanation and try_marker in explanation:
                before, remainder = explanation.split(why_marker, 1)
                _old_why, after = remainder.split(try_marker, 1)
                explanation = (
                    before
                    + why_marker
                    + _UNMODELED_CONTROL_NOTE
                    + "\n- The selected configuration has design tradeoffs, but "
                    "the telemetry does not prove which one prevented recovery."
                    + try_marker
                    + after
                )
            rewritten.append(replace(mission, explanation=explanation))
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


def install_tutorial_report_guard() -> None:
    """Install the report corrections exactly once."""
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
        launch_handler.chart_to_string = _fenced_chart(
            launch_handler.chart_to_string
        )
