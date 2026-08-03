"""Powered-flight model for the introductory buoyancy-assisted quadcopter."""

from __future__ import annotations

from dataclasses import dataclass, replace

from balloon_frontier.flight_score import calculate_flight_score
from balloon_frontier.launch_result import FlightResult, TelemetryPoint
from balloon_frontier.medal_tier import get_medal_emoji, medal_tier_to_string

PHOTO_ALTITUDE_M = 30.0
PHOTO_HOLD_TIME_S = 45.0
PHOTO_ROUTE_TIME_S = 210.0
BASELINE_ENDURANCE_S = 150.0
IDLE_POWER_FRACTION = 0.22


@dataclass(frozen=True)
class PoweredFlightAssessment:
    eligible: bool
    supported_fraction: float = 0.0
    rotor_load_fraction: float = 1.0
    power_fraction: float = 1.0
    estimated_endurance_s: float = BASELINE_ENDURANCE_S
    route_time_s: float = PHOTO_ROUTE_TIME_S

    @property
    def can_complete_route(self) -> bool:
        return self.eligible and self.estimated_endurance_s >= self.route_time_s


def assess_tutorial_powered_flight(request, outcome) -> PoweredFlightAssessment:
    """Assess a passive ground contact as a powered quadcopter launch.

    Genuine burst and crash outcomes are never eligible for substitution. The
    first passive telemetry point supplies the actual configured mass,
    buoyancy, atmosphere, gas volume, and added equipment mass.
    """
    result = outcome.result
    points = tuple(getattr(result, "telemetry", ()) or ())
    passive_grounding = (
        "quadcopter" in set(request.payload_ids)
        and bool(getattr(result, "landed", False))
        and not bool(getattr(result, "burst", False))
        and not bool(getattr(result, "crashed", False))
        and float(getattr(result, "duration_s", 0.0)) <= 0.1
        and float(getattr(result, "peak_altitude_m", 0.0)) <= 0.1
        and bool(points)
        and hasattr(points[0], "weight_N")
        and hasattr(points[0], "buoyancy_N")
        and hasattr(points[0], "gas_volume_m3")
    )
    if not passive_grounding:
        return PoweredFlightAssessment(eligible=False)

    first = points[0]
    weight_n = max(float(first.weight_N), 1e-9)
    buoyancy_n = max(0.0, float(first.buoyancy_N))
    supported_fraction = min(1.0, buoyancy_n / weight_n)
    rotor_load_fraction = max(0.0, 1.0 - supported_fraction)

    # Induced hover power scales approximately with thrust^(3/2), while motors,
    # avionics, and control corrections impose a nonzero power floor.
    induced_fraction = rotor_load_fraction ** 1.5
    power_fraction = IDLE_POWER_FRACTION + (1.0 - IDLE_POWER_FRACTION) * induced_fraction

    # Larger and draggier envelopes consume additional control power. This is a
    # deliberately small penalty; it does not pretend to be a full propulsor CFD
    # model, but it makes actual envelope choices affect endurance.
    envelope = request.envelope
    drag_penalty = min(
        0.25,
        0.025 * float(envelope.drag_coefficient) * float(first.gas_volume_m3) ** (2.0 / 3.0),
    )
    power_fraction = min(1.5, power_fraction + drag_penalty)
    estimated_endurance_s = BASELINE_ENDURANCE_S / max(power_fraction, 1e-6)

    return PoweredFlightAssessment(
        eligible=True,
        supported_fraction=supported_fraction,
        rotor_load_fraction=rotor_load_fraction,
        power_fraction=power_fraction,
        estimated_endurance_s=estimated_endurance_s,
    )


def tutorial_photo_captured(result) -> bool:
    """Require a sustained, timestamped camera hold at school-photo altitude."""
    points = tuple(getattr(result, "telemetry", ()) or ())
    if len(points) < 2:
        return False

    dwell_s = 0.0
    for previous, current in zip(points, points[1:]):
        previous_time = getattr(previous, "time_s", None)
        current_time = getattr(current, "time_s", None)
        if previous_time is None or current_time is None:
            return False
        if (
            float(previous.altitude_m) >= PHOTO_ALTITUDE_M
            and float(current.altitude_m) >= PHOTO_ALTITUDE_M
        ):
            dwell_s += max(0.0, float(current_time) - float(previous_time))
    return dwell_s >= PHOTO_HOLD_TIME_S


def apply_tutorial_powered_flight(request, outcome, assessment=None):
    """Generate a powered sortie only when the measured energy budget permits it."""
    assessment = assessment or assess_tutorial_powered_flight(request, outcome)
    if not assessment.can_complete_route:
        return outcome

    result = outcome.result
    first = tuple(result.telemetry)[0]
    total_mass = float(first.total_mass_kg)
    gas_mass = float(first.gas_mass_kg)
    buoyancy_n = float(first.buoyancy_N)
    weight_n = float(first.weight_N)
    gas_volume = float(first.gas_volume_m3)
    pressure = float(first.ambient_pressure_pa)
    temperature = float(first.ambient_temperature_k)

    def point(time_s, altitude_m, velocity_mps, x_m, *, landed=False):
        return TelemetryPoint(
            time_s=time_s,
            altitude_m=altitude_m,
            velocity_mps=velocity_mps,
            gas_volume_m3=gas_volume,
            ambient_pressure_pa=pressure,
            ambient_temperature_k=temperature,
            # This interim profile is kinematic. Force fields retain their
            # ordinary meanings and are not repurposed to represent rotor thrust.
            net_lift_N=0.0,
            buoyancy_N=buoyancy_n,
            weight_N=weight_n,
            drag_N=0.0,
            gas_mass_kg=gas_mass,
            total_mass_kg=total_mass,
            landed=landed,
            x_m=x_m,
        )

    points = (
        point(0.0, 0.0, 0.0, 0.0),
        point(45.0, 32.0, 0.8, 70.0),
        point(120.0, 38.0, 0.0, 120.0),
        point(PHOTO_ROUTE_TIME_S, 0.0, -0.5, 0.0, landed=True),
    )
    powered_result = FlightResult(telemetry=points, launch_request=result.launch_request)
    peak = powered_result.peak_altitude_m
    score = calculate_flight_score(peak, 1, powered_result.duration_s)
    return replace(
        outcome,
        result=powered_result,
        score=score,
        medal_name=medal_tier_to_string(peak),
        medal_emoji=get_medal_emoji(peak),
    )
