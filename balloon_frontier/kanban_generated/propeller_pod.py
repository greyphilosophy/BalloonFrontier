from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


G_DEFAULT_M_S2 = 9.81


def _clamp(x: float, lo: float, hi: float) -> float:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _clamp_cmd(x: float) -> float:
    """Clamp a normalized control command into [-1, 1]."""
    return _clamp(x, -1.0, 1.0)


@dataclass
class AltitudePIDController:
    """A small stateful altitude PID controller.

    Units
    -----
    - altitude: meters
    - vertical_speed: m/s (positive = upward)
    - thrust: Newtons

    Control law
    ------------
    thrust_n = clamp(hover_thrust + kp*error + ki*integral(error) - kd*vertical_speed)

    The derivative term is implemented as -kd * vertical_speed so that an
    ascending vehicle gets a damping (reduced thrust) and a descending one
    gets less damping (increased thrust).
    """

    mass_kg: float
    max_thrust_n: float
    kp: float
    ki: float = 0.0
    kd: float = 0.0

    g_m_s2: float = G_DEFAULT_M_S2
    integral_error_m_s: float = 0.0
    integral_error_limit_m_s: Optional[float] = None

    def reset(self) -> None:
        self.integral_error_m_s = 0.0

    @property
    def hover_thrust_n(self) -> float:
        return self.mass_kg * self.g_m_s2

    def update(
        self,
        *,
        dt_s: float,
        target_altitude_m: float,
        altitude_m: float,
        vertical_speed_m_s: float,
    ) -> float:
        if dt_s <= 0:
            raise ValueError("dt_s must be positive")

        error_m = target_altitude_m - altitude_m

        # Integrator update (anti-windup via clamping integral contribution).
        self.integral_error_m_s += error_m * dt_s
        if self.integral_error_limit_m_s is not None:
            self.integral_error_m_s = _clamp(
                self.integral_error_m_s,
                -self.integral_error_limit_m_s,
                self.integral_error_limit_m_s,
            )

        thrust_delta_n = (
            self.kp * error_m
            + self.ki * self.integral_error_m_s
            - self.kd * vertical_speed_m_s
        )
        thrust_n = self.hover_thrust_n + thrust_delta_n
        return _clamp(thrust_n, 0.0, self.max_thrust_n)


@dataclass(frozen=True)
class PropellerPodConfig:
    """Configuration for propeller thrust, attitude authority, and power."""

    mass_kg: float
    max_thrust_n: float

    # Power model (electrical) parameters.
    power_idle_w: float = 25.0
    power_max_w: float = 250.0
    power_exponent: float = 2.0

    # Additional power for maneuvering/attitude control.
    maneuver_power_scale_w: float = 40.0

    # Moment authority at full (normalized) thrust.
    pitch_moment_nm_max: float = 10.0
    roll_moment_nm_max: float = 8.0
    yaw_moment_nm_max: float = 6.0

    # Altitude controller defaults (callers can override with their own gains).
    altitude_pid_kp: float = 2.0
    altitude_pid_ki: float = 0.0
    altitude_pid_kd: float = 0.0
    altitude_pid_integral_error_limit_m_s: Optional[float] = None


@dataclass(frozen=True)
class PropellerCommandResult:
    thrust_n: float
    thrust_fraction: float
    pitch_moment_nm: float
    roll_moment_nm: float
    yaw_moment_nm: float
    power_w: float


class PropellerPod:
    """A deterministic propeller pod model.

    The pod provides:
    - altitude control via an internal PID controller
    - maneuverability via direct pitch/roll/yaw moment authority
    - a simplified electrical power consumption model
    """

    def __init__(
        self,
        *,
        config: PropellerPodConfig,
        altitude_controller: Optional[AltitudePIDController] = None,
    ) -> None:
        if config.mass_kg <= 0:
            raise ValueError("config.mass_kg must be positive")
        if config.max_thrust_n <= 0:
            raise ValueError("config.max_thrust_n must be positive")
        if config.power_idle_w < 0 or config.power_max_w < 0:
            raise ValueError("power values must be non-negative")
        if config.power_exponent <= 0:
            raise ValueError("power_exponent must be positive")

        self.config = config
        self.altitude_controller = (
            altitude_controller
            if altitude_controller is not None
            else AltitudePIDController(
                mass_kg=config.mass_kg,
                max_thrust_n=config.max_thrust_n,
                kp=config.altitude_pid_kp,
                ki=config.altitude_pid_ki,
                kd=config.altitude_pid_kd,
                integral_error_limit_m_s=config.altitude_pid_integral_error_limit_m_s,
            )
        )

    def compute_moments(
        self,
        *,
        thrust_fraction: float,
        pitch_cmd: float = 0.0,
        roll_cmd: float = 0.0,
        yaw_cmd: float = 0.0,
    ) -> Tuple[float, float, float]:
        thrust_fraction = _clamp(thrust_fraction, 0.0, 1.0)
        pitch_cmd = _clamp_cmd(pitch_cmd)
        roll_cmd = _clamp_cmd(roll_cmd)
        yaw_cmd = _clamp_cmd(yaw_cmd)

        pitch_nm = pitch_cmd * self.config.pitch_moment_nm_max * thrust_fraction
        roll_nm = roll_cmd * self.config.roll_moment_nm_max * thrust_fraction
        yaw_nm = yaw_cmd * self.config.yaw_moment_nm_max * thrust_fraction
        return pitch_nm, roll_nm, yaw_nm

    def compute_power_w(
        self,
        *,
        thrust_fraction: float,
        pitch_cmd: float = 0.0,
        roll_cmd: float = 0.0,
        yaw_cmd: float = 0.0,
    ) -> float:
        thrust_fraction = _clamp(thrust_fraction, 0.0, 1.0)
        base = self.config.power_idle_w
        climb = (thrust_fraction**self.config.power_exponent) * (
            self.config.power_max_w - self.config.power_idle_w
        )

        pitch_cmd = _clamp_cmd(pitch_cmd)
        roll_cmd = _clamp_cmd(roll_cmd)
        yaw_cmd = _clamp_cmd(yaw_cmd)
        maneuver = self.config.maneuver_power_scale_w * (
            pitch_cmd**2 + roll_cmd**2 + yaw_cmd**2
        )

        return base + climb + maneuver

    def command(
        self,
        *,
        dt_s: float,
        target_altitude_m: float,
        altitude_m: float,
        vertical_speed_m_s: float,
        pitch_cmd: float = 0.0,
        roll_cmd: float = 0.0,
        yaw_cmd: float = 0.0,
    ) -> PropellerCommandResult:
        thrust_n = self.altitude_controller.update(
            dt_s=dt_s,
            target_altitude_m=target_altitude_m,
            altitude_m=altitude_m,
            vertical_speed_m_s=vertical_speed_m_s,
        )
        thrust_fraction = thrust_n / self.config.max_thrust_n

        pitch_nm, roll_nm, yaw_nm = self.compute_moments(
            thrust_fraction=thrust_fraction,
            pitch_cmd=pitch_cmd,
            roll_cmd=roll_cmd,
            yaw_cmd=yaw_cmd,
        )
        power_w = self.compute_power_w(
            thrust_fraction=thrust_fraction,
            pitch_cmd=pitch_cmd,
            roll_cmd=roll_cmd,
            yaw_cmd=yaw_cmd,
        )

        return PropellerCommandResult(
            thrust_n=thrust_n,
            thrust_fraction=thrust_fraction,
            pitch_moment_nm=pitch_nm,
            roll_moment_nm=roll_nm,
            yaw_moment_nm=yaw_nm,
            power_w=power_w,
        )

    def step_vertical_dynamics(
        self,
        *,
        altitude_m: float,
        vertical_speed_m_s: float,
        thrust_n: float,
        dt_s: float,
    ) -> Tuple[float, float]:
        """Propagate altitude/vertical-speed for one dt using explicit Euler."""
        if dt_s <= 0:
            raise ValueError("dt_s must be positive")
        if self.config.mass_kg <= 0:
            raise ValueError("config.mass_kg must be positive")

        thrust_n = _clamp(thrust_n, 0.0, self.config.max_thrust_n)

        accel_m_s2 = thrust_n / self.config.mass_kg - self.altitude_controller.g_m_s2
        new_vertical_speed = vertical_speed_m_s + accel_m_s2 * dt_s
        new_altitude = altitude_m + new_vertical_speed * dt_s
        return new_altitude, new_vertical_speed
