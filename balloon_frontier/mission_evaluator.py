"""Balloon Frontier — Mission Evaluation Engine

Pure game-rules component that judges mission outcomes from flight telemetry.
Safety policy is deliberately kept here rather than in physics: risky methods
remain simulatable, while individual missions may prohibit selected risk tags.
"""

from __future__ import annotations

import logging
from typing import Optional

from balloon_frontier.aerostat import (
    risk_tags_for_request,
    safety_notes_for_request,
)
from balloon_frontier.launch_result import (
    LaunchRequest,
    TelemetryPoint,
    MissionAssignment,
    MissionResult,
)

logger = logging.getLogger(__name__)


def _peak_altitude_within_horizontal_radius(
    telemetry: tuple[TelemetryPoint, ...],
    max_distance_m: float,
) -> float:
    """Return peak altitude reached while remaining near the launch/target area."""
    radius_m = max(0.0, float(max_distance_m))
    return max(
        (
            point.altitude_m
            for point in telemetry
            if abs(point.x_m) <= radius_m
        ),
        default=0.0,
    )


class MissionEvaluator:
    """Pure game-rules evaluator that judges mission outcomes from telemetry."""

    def __init__(
        self,
        mission_catalog: Optional[dict] = None,
    ) -> None:
        from balloon_frontier.missions import MISSIONS

        self.mission_catalog = mission_catalog if mission_catalog is not None else MISSIONS

    def evaluate(
        self,
        request: LaunchRequest,
        telemetry: tuple[TelemetryPoint, ...],
        assignment: MissionAssignment,
    ) -> tuple[MissionResult, ...]:
        """Evaluate all assigned missions and return their results."""
        if not assignment.mission_ids:
            return ()

        results: list[MissionResult] = []
        peak_altitude = max((tp.altitude_m for tp in telemetry), default=0.0)
        duration_s = telemetry[-1].time_s if telemetry else 0.0
        has_landed = any(tp.landed for tp in telemetry)
        has_crashed = any(tp.crashed for tp in telemetry)
        burst = any(tp.burst for tp in telemetry)

        if telemetry and len(telemetry) > 1:
            distance_travelled_m = abs(telemetry[-1].x_m - telemetry[0].x_m)
        else:
            distance_travelled_m = 0.0

        selected_payloads = frozenset(
            pid for pid in request.payload_ids if pid != "none"
        )
        selected_risks = risk_tags_for_request(request)
        safety_notes = safety_notes_for_request(request)

        for mission_id in assignment.mission_ids:
            mission = self.mission_catalog.get(mission_id)
            if mission is None:
                results.append(MissionResult(
                    mission_id=mission_id,
                    completed=False,
                    reward=0,
                    explanation=f"Mission {mission_id} not found",
                ))
                continue

            required_payloads = frozenset(mission.required_payloads)
            if not required_payloads.issubset(selected_payloads):
                missing = required_payloads - selected_payloads
                results.append(MissionResult(
                    mission_id=mission_id,
                    completed=False,
                    reward=0,
                    explanation=(
                        f"Mission {mission_id} failed: missing required payloads: "
                        f"{', '.join(sorted(missing))}"
                    ),
                ))
                continue

            if request.launch_site_id != mission.launch_site:
                results.append(MissionResult(
                    mission_id=mission_id,
                    completed=False,
                    reward=0,
                    explanation=(
                        f"Mission {mission_id} failed: launch site "
                        f"{request.launch_site_id!r} does not match required site "
                        f"{mission.launch_site!r}"
                    ),
                ))
                continue

            prohibited = frozenset(
                getattr(mission, "prohibited_risk_tags", ()) or ()
            )
            blocked = selected_risks & prohibited
            if blocked:
                explanation = (
                    f"Mission {mission.title} does not permit this configuration: "
                    f"prohibited risk tags {', '.join(sorted(blocked))}."
                )
                if safety_notes:
                    explanation += " Safety notes: " + " ".join(safety_notes)
                results.append(MissionResult(
                    mission_id=mission_id,
                    completed=False,
                    reward=0,
                    explanation=explanation,
                ))
                continue

            completed = self._check_mission_completion(
                mission=mission,
                peak_altitude=peak_altitude,
                duration=duration_s,
                has_landed=has_landed,
                has_crashed=has_crashed,
                burst=burst,
                telemetry=telemetry,
                distance_travelled_m=distance_travelled_m,
                selected_payloads=selected_payloads,
                mission_id=mission_id,
            )

            reward = mission.budget if completed else 0
            explanation = self._generate_mission_explanation(
                mission=mission,
                completed=completed,
                peak_altitude=peak_altitude,
            )
            if safety_notes:
                explanation += " Safety notes: " + " ".join(safety_notes)

            results.append(MissionResult(
                mission_id=mission_id,
                completed=completed,
                reward=reward,
                explanation=explanation,
            ))

        return tuple(results)

    def _check_mission_completion(
        self,
        mission,
        peak_altitude: float,
        duration: float,
        has_landed: bool,
        has_crashed: bool,
        burst: bool,
        telemetry: tuple[TelemetryPoint, ...],
        distance_travelled_m: float,
        selected_payloads: frozenset[str],
        mission_id: str,
    ) -> bool:
        """Check all objectives for a single mission."""
        for objective in mission.objectives:
            if not self._evaluate_objective(
                objective=objective,
                peak_altitude=peak_altitude,
                duration=duration,
                has_landed=has_landed,
                has_crashed=has_crashed,
                burst=burst,
                telemetry=telemetry,
                distance_travelled_m=distance_travelled_m,
                selected_payloads=selected_payloads,
                mission_id=mission_id,
            ):
                return False
        return True

    def _evaluate_objective(
        self,
        objective,
        peak_altitude: float,
        duration: float,
        has_landed: bool,
        has_crashed: bool,
        burst: bool,
        telemetry: tuple[TelemetryPoint, ...],
        distance_travelled_m: float,
        selected_payloads: frozenset[str],
        mission_id: str,
    ) -> bool:
        """Evaluate a single objective against telemetry."""
        obj_type = objective.type

        if obj_type == "reach_altitude":
            minimum_m = objective.params.get("minimum_m", 0)
            return peak_altitude >= minimum_m

        if obj_type == "recover_data":
            return has_landed and not has_crashed

        if obj_type == "capture_photo":
            if "camera" not in selected_payloads:
                return False
            min_quality = objective.params.get("minimum_quality", 0.5)
            photo_peak_altitude = peak_altitude
            max_horizontal_distance_m = objective.params.get(
                "max_horizontal_distance_m"
            )
            if max_horizontal_distance_m is not None:
                photo_peak_altitude = _peak_altitude_within_horizontal_radius(
                    telemetry,
                    max_horizontal_distance_m,
                )
            quality = min(photo_peak_altitude / 50000.0, 1.0)
            if burst:
                quality *= 0.5
            return quality >= min_quality

        if obj_type == "float_duration":
            target_hours = objective.params.get("target_hours", 0)
            return duration / 3600.0 >= target_hours

        if obj_type == "station_keep":
            target_alt = objective.params.get("target_altitude_m", 0)
            tolerance = 500.0
            if not telemetry:
                return False
            in_range_steps = sum(
                1 for tp in telemetry
                if abs(tp.altitude_m - target_alt) <= tolerance
            )
            return in_range_steps / max(len(telemetry), 1) >= 0.5

        if obj_type == "fly_distance":
            minimum_m = objective.params.get("minimum_m", 0)
            return distance_travelled_m >= minimum_m

        logger.error(
            "Unsupported mission objective type '%s' in mission '%s'. "
            "Objective will cause mission failure.",
            obj_type,
            mission_id,
        )
        return False

    @staticmethod
    def _generate_mission_explanation(
        mission,
        completed: bool,
        peak_altitude: float,
    ) -> str:
        """Generate a human-readable explanation for mission result."""
        if completed:
            return (
                f"Mission {mission.title} completed! "
                f"Budget {mission.budget} credits awarded."
            )
        return f"Mission {mission.title} not completed. No budget awarded."


mission_evaluator = MissionEvaluator()
