"""Balloon Frontier — Mission Evaluation Engine

Pure game-rules component that judges mission outcomes from flight telemetry.
No persistence, no simulation — only the rules that decide whether missions pass.

## Public API

```python
evaluator = MissionEvaluator()
results = evaluator.evaluate(launch_request, telemetry, mission_assignment)
```

## Design

`MissionEvaluator` owns one responsibility: given the flight telemetry,
decide whether each assigned mission's objectives were satisfied.

It is a *pure* function of its inputs plus the mission catalog:
- No I/O
- No side-effects
- Deterministic — same inputs always yield the same outcomes

### Objective types

| Type              | Required condition                                   |
|-------------------|------------------------------------------------------|
| `reach_altitude`  | peak altitude ≥ minimum_m                            |
| `recover_data`    | landed=True and crashed=False                        |
| `capture_photo`   | camera payload present AND quality ≥ minimum_quality  |
| `float_duration`  | flight duration ≥ target_hours (hours)               |
| `station_keep`    | ≥ 50 % of telemetry steps within ± 500 m of target   |
| `fly_distance`    | horizontal distance ≥ minimum_m                      |

Unknown objective types fail closed (mission fails with error logged).
"""

from __future__ import annotations

import logging
from typing import Optional

from balloon_frontier.launch_result import (
    LaunchRequest,
    TelemetryPoint,
    MissionAssignment,
    MissionResult,
)

logger = logging.getLogger(__name__)


class MissionEvaluator:
    """Pure game-rules evaluator that judges mission outcomes from telemetry.

    Attributes:
        mission_catalog: Mapping of mission id → mission data.  Defaults to
            :data:`balloon_frontier.missions.MISSIONS`.
    """

    def __init__(
        self,
        mission_catalog: Optional[dict] = None,
    ) -> None:
        from balloon_frontier.missions import MISSIONS

        self.mission_catalog = mission_catalog if mission_catalog is not None else MISSIONS

    # ── public entry point ────────────────────────────────────────────

    def evaluate(
        self,
        request: LaunchRequest,
        telemetry: tuple[TelemetryPoint, ...],
        assignment: MissionAssignment,
    ) -> tuple[MissionResult, ...]:
        """Evaluate all assigned missions and return their results.

        This is the only public method.  It orchestrates config-level
        checks (required payloads, launch site), objective evaluation,
        and result assembly.

        Args:
            request: The launch configuration (for payload/site checks).
            telemetry: Flight telemetry (for objective checks).
            assignment: Which missions were assigned to this flight.

        Returns:
            Tuple of ``MissionResult`` objects — one per assigned mission id,
            in the same order.
        """
        if not assignment.mission_ids:
            return ()

        results: list[MissionResult] = []

        # Pre-compute per-telemetry aggregates (avoid repeated scans)
        peak_altitude: float = (
            max((tp.altitude_m for tp in telemetry), default=0.0)
        )
        duration_s: float = telemetry[-1].time_s if telemetry else 0.0
        has_landed: bool = any(tp.landed for tp in telemetry)
        has_crashed: bool = any(tp.crashed for tp in telemetry)
        burst: bool = any(tp.burst for tp in telemetry)

        # Pre-compute horizontal distance (for fly_distance)
        if telemetry and len(telemetry) > 1:
            start_x = telemetry[0].x_m
            end_x = telemetry[-1].x_m
            distance_travelled_m: float = abs(end_x - start_x)
        else:
            distance_travelled_m = 0.0

        # Build selected payload set once (for required_payloads + capture_photo)
        selected_payloads = frozenset(
            pid for pid in request.payload_ids if pid != "none"
        )

        for mission_id in assignment.mission_ids:
            mission = self.mission_catalog.get(mission_id)

            # ── Unknown mission → fail closed ────────────────────
            if mission is None:
                results.append(MissionResult(
                    mission_id=mission_id,
                    completed=False,
                    reward=0,
                    explanation=f"Mission {mission_id} not found",
                ))
                continue

            # ── Config check: required payloads ──────────────────
            required_payloads = frozenset(mission.required_payloads)
            if not required_payloads.issubset(selected_payloads):
                missing = required_payloads - selected_payloads
                results.append(MissionResult(
                    mission_id=mission_id,
                    completed=False,
                    reward=0,
                    explanation=(
                        f"Mission {mission_id} failed: "
                        f"missing required payloads: "
                        f"{', '.join(sorted(missing))}"
                    ),
                ))
                continue

            # ── Config check: launch site ────────────────────────
            if request.launch_site_id != mission.launch_site:
                results.append(MissionResult(
                    mission_id=mission_id,
                    completed=False,
                    reward=0,
                    explanation=(
                        f"Mission {mission_id} failed: "
                        f"launch site {request.launch_site_id!r} "
                        f"does not match required site {mission.launch_site!r}"
                    ),
                ))
                continue

            # ── Objective evaluation ─────────────────────────────
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

            results.append(MissionResult(
                mission_id=mission_id,
                completed=completed,
                reward=reward,
                explanation=explanation,
            ))

        return tuple(results)

    # ── private helpers ────────────────────────────────────────────────

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
        """Check all objectives for a single mission.

        All objectives must pass; if any fails, the mission fails.
        Unknown objective types fail closed.
        """
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
        """Evaluate a single objective against the telemetry.

        Returns True if the objective is satisfied, False otherwise.
        Unknown objective types log an error and return False.
        """
        obj_type = objective.type

        if obj_type == "reach_altitude":
            minimum_m = objective.params.get("minimum_m", 0)
            return peak_altitude >= minimum_m

        if obj_type == "recover_data":
            return has_landed and not has_crashed

        if obj_type == "capture_photo":
            # Requires camera payload in launch config
            if "camera" not in selected_payloads:
                return False

            # Quality scales with altitude up to 1.0 at 50 000 m
            min_quality = objective.params.get("minimum_quality", 0.5)
            quality = min(peak_altitude / 50000.0, 1.0)
            if burst:
                quality *= 0.5
            return quality >= min_quality

        if obj_type == "float_duration":
            target_hours = objective.params.get("target_hours", 0)
            actual_hours = duration / 3600.0
            return actual_hours >= target_hours

        if obj_type == "station_keep":
            # Percentage of steps within ± 500 m of target altitude
            target_alt = objective.params.get("target_altitude_m", 0)
            tolerance = 500.0
            if not telemetry:
                return False
            in_range_steps = sum(
                1 for tp in telemetry
                if abs(tp.altitude_m - target_alt) <= tolerance
            )
            max_steps = max(len(telemetry), 1)
            fraction = in_range_steps / max_steps
            return fraction >= 0.5

        if obj_type == "fly_distance":
            minimum_m = objective.params.get("minimum_m", 0)
            return distance_travelled_m >= minimum_m

        # Unknown objective type — fail closed
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


# ── Module-level singleton (for convenience) ─────────────────────────

mission_evaluator = MissionEvaluator()