"""Balloon Frontier - Mission Evaluation System

Evaluates a completed flight against mission objectives, producing
scores for each objective and an overall mission result.

Reference: GDD Sections 14.2, 17.
"""

from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Objective:
    """A single mission objective."""
    type: str
    target_value: float
    actual_value: float
    weight: float = 1.0
    description: str = ""

@dataclass
class MissionResult:
    """Result of evaluating a flight against a mission."""
    mission_id: str
    score: float
    objectives: List[Objective]
    is_success: bool
    notes: str = ""

def evaluate_objective(obj: Objective) -> float:
    """Score a single objective (0-100)."""
    if obj.type == "reach_altitude":
        if obj.actual_value >= obj.target_value:
            return 100.0
        return obj.actual_value / obj.target_value * 100

    elif obj.type == "capture_photo":
        return min(obj.actual_value * 100, 100.0)

    elif obj.type == "recover_data":
        return min(obj.actual_value * 100, 100.0)

    elif obj.type == "float_duration":
        return min(obj.actual_value / obj.target_value * 100, 100.0)

    elif obj.type == "station_keep":
        return min(obj.actual_value / obj.target_value * 100, 100.0)

    return 50.0

def evaluate_flight(
    telemetry: List[dict],
    mission_config: dict,
    payloads: Optional[List[str]] = None,
) -> MissionResult:
    """Evaluate a complete flight against mission objectives."""
    objectives = []
    notes = []
    total_weight = 0.0
    weighted_score = 0.0

    peak_altitude = max(t["altitude_m"] for t in telemetry)
    final_step = telemetry[-1]
    flight_duration = telemetry[-1].get("time_s", 0)
    burst = final_step.get("burst", False)

    for obj_config in mission_config.get("objectives", []):
        obj_type = obj_config["type"]
        target = obj_config.get("target_value", 0)
        weight = obj_config.get("weight", 1.0)

        if obj_type == "reach_altitude":
            obj = Objective("reach_altitude", target, peak_altitude, weight)
            notes.append(f"Reached {peak_altitude:.0f}m (target: {target:.0f}m)")

        elif obj_type == "capture_photo":
            has_camera = payloads and "camera" in payloads
            photo_quality = 0.0
            if has_camera:
                quality = min(peak_altitude / (target or 100), 1.0)
                if burst:
                    quality *= 0.5
                photo_quality = quality
            obj = Objective("capture_photo", 1.0, photo_quality, weight)
            notes.append(f"Photo quality: {photo_quality:.2f}")

        elif obj_type == "recover_data":
            has_gps = payloads and "gps_receiver" in payloads
            recovery = 0.5 if burst else 0.8
            if has_gps:
                recovery = max(recovery, 0.6)
            obj = Objective("recover_data", 1.0, recovery, weight)
            notes.append(f"Data recovery: {recovery:.2f}")

        elif obj_type == "float_duration":
            target_hours = target
            actual_hours = flight_duration / 3600
            obj = Objective("float_duration", target_hours, actual_hours, weight)
            notes.append(f"Duration: {actual_hours:.1f}h")

        elif obj_type == "station_keep":
            target_alt = target
            in_range_steps = sum(
                1 for t in telemetry
                if abs(t["altitude_m"] - target_alt) <= 500
            )
            max_steps = len(telemetry)
            fraction = in_range_steps / max_steps if max_steps > 0 else 0
            obj = Objective("station_keep", max_steps, fraction, weight)
            notes.append(f"Station kept: {in_range_steps} steps")

        else:
            continue

        objectives.append(obj)
        score = evaluate_objective(obj)
        weighted_score += score * obj.weight
        total_weight += obj.weight

    overall_score = (weighted_score / total_weight) if total_weight > 0 else 0
    is_success = overall_score >= 60

    return MissionResult(
        mission_id=mission_config.get("id", "unknown"),
        score=overall_score,
        objectives=objectives,
        is_success=is_success,
        notes="; ".join(notes),
    )

def format_mission_result(result: MissionResult) -> str:
    """Format a mission result as text summary."""
    lines = [
        f"Mission: {result.mission_id}",
        f"Score: {result.score:.1f}/100",
        "",
    ]
    for obj in result.objectives:
        score = evaluate_objective(obj)
        icon = "PASS" if score >= 80 else "PARTIAL" if score >= 50 else "SCORE"
        lines.append(f"  {icon} {score:.0f}/100: {obj.description or obj.type}")
    if result.notes:
        lines.append(f"Notes: {result.notes}")
    return "\n".join(lines)
