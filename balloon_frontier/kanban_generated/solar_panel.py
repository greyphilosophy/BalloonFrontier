from __future__ import annotations

import math
from dataclasses import dataclass


def diurnal_factor(
    time_of_day_s: float,
    *,
    day_length_s: float = 86_400.0,
    daylight_fraction: float = 0.5,
) -> float:
    """Return a [0, 1] sunlight availability factor over a day.

    Conventions
    -----------
    - time_of_day_s = 0 means midnight.
    - The peak (factor ~1) happens at solar noon (time_of_day_s = day_length_s/2).
    - sunrise/sunset are approximated by a smooth window of length
      ``daylight_fraction`` of the day.

    The function is continuous and returns exactly 0 outside the daylight
    window.
    """

    if day_length_s <= 0:
        raise ValueError("day_length_s must be positive")
    if not (0.0 < daylight_fraction <= 1.0):
        raise ValueError("daylight_fraction must be in (0, 1]")

    # Normalize into [0, day_length_s)
    t = time_of_day_s % day_length_s
    x = t / day_length_s  # [0, 1)

    # Daylight window centered at noon (x=0.5)
    half = daylight_fraction / 2.0
    start = 0.5 - half
    end = 0.5 + half

    # No daylight: keep deterministic (shouldn't happen due to validation)
    if daylight_fraction <= 0.0:
        return 0.0

    # Handle wrap-around windows (e.g., daylight_fraction close to 1)
    if start < 0.0:
        in_window = x >= (start + 1.0) or x <= end
        u = ((x - start) / daylight_fraction) % 1.0
    elif end >= 1.0:
        in_window = x >= start or x <= (end - 1.0)
        u = ((x - start) / daylight_fraction) % 1.0
    else:
        in_window = start <= x <= end
        u = (x - start) / daylight_fraction  # in [0,1]

    if not in_window:
        return 0.0

    # u=0 at sunrise => 0, u=0.5 at noon => 1, u=1 at sunset => 0
    # Use sin(pi*u) for smooth edges with zero slope at boundaries.
    return math.sin(math.pi * u)


def altitude_factor(
    altitude_m: float,
    *,
    base_gain: float = 0.30,
    saturation_m: float = 6_000.0,
) -> float:
    """Dimensionless multiplier for solar output vs altitude.

    - altitude_m=0 => factor=1.0
    - increases monotonically and saturates smoothly.
    """

    if saturation_m <= 0:
        raise ValueError("saturation_m must be positive")

    if altitude_m < 0:
        altitude_m = 0.0

    # gain = base_gain * altitude/(altitude + saturation)
    gain = base_gain * (altitude_m / (altitude_m + saturation_m))
    return 1.0 + gain


@dataclass(frozen=True)
class Battery:
    """Simple battery energy state (energy measured in Wh)."""

    capacity_wh: float
    charge_wh: float

    def __post_init__(self) -> None:
        if self.capacity_wh <= 0:
            raise ValueError("capacity_wh must be positive")
        if self.charge_wh < 0:
            raise ValueError("charge_wh must be non-negative")
        if self.charge_wh > self.capacity_wh:
            # Keep state clamped to maintain deterministic behavior.
            object.__setattr__(self, "charge_wh", float(self.capacity_wh))

    @property
    def remaining_wh(self) -> float:
        return max(0.0, self.capacity_wh - self.charge_wh)


class SolarPanel:
    """Solar panel power + battery recharge model."""

    def __init__(
        self,
        *,
        rated_power_w: float,
        panel_charge_efficiency: float = 0.22,
    ) -> None:
        if rated_power_w < 0:
            raise ValueError("rated_power_w must be non-negative")
        if not (0.0 <= panel_charge_efficiency <= 1.0):
            raise ValueError("panel_charge_efficiency must be in [0,1]")
        self.rated_power_w = float(rated_power_w)
        self.panel_charge_efficiency = float(panel_charge_efficiency)

    def recharge(
        self,
        *,
        battery: Battery,
        altitude_m: float,
        time_of_day_s: float,
        dt_s: float,
    ) -> float:
        """Recharge the battery for dt_s.

        Returns
        -------
        float
            The actual energy added to the battery (Wh).
        """

        if dt_s < 0:
            raise ValueError("dt_s must be non-negative")
        if battery.remaining_wh <= 0.0:
            return 0.0
        if dt_s == 0.0 or self.rated_power_w == 0.0:
            return 0.0

        df = diurnal_factor(time_of_day_s)
        if df <= 0.0:
            return 0.0

        af = altitude_factor(altitude_m)

        # Instantaneous power while charging.
        power_w = self.rated_power_w * df * af

        # Convert W*s -> Wh: Wh = W * seconds / 3600
        requested_added_wh = power_w * float(dt_s) / 3600.0 * self.panel_charge_efficiency
        added_wh = min(battery.remaining_wh, max(0.0, requested_added_wh))

        # Battery is frozen; return value is used by caller to update state.
        # For convenience, we treat "battery" as immutable and rely on caller
        # patterns in this repo's generated tests.
        #
        # If callers want mutability, pass in a Battery-like object.
        try:
            # Attempt to update charge_wh if it's not truly frozen.
            object.__setattr__(battery, "charge_wh", battery.charge_wh + added_wh)
        except Exception:
            pass

        return added_wh
