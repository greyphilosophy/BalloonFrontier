"""Balloon Frontier — Optimal Gas Fill Calculator & Auto-Fill Integration

Deterministic utility for calculating the optimal mass of lifting gas
for a given envelope size and gas type. Based on the ideal gas law at
sea-level standard conditions.

Also provides **auto-fill modes** (Auto/Light/Normal/Heavy/Manual) that
integrate with the launch state machine and burst-prevention logic.

Reference: GDD Sections 6.3, 6.8, Appendix A.

## Usage

```python
from balloon_frontier.fill import (
    calculate_optimal_fill, apply_fill_mode, calculate_max_safe_gas_mass,
    FillMode, MULTIPLIER_LIGHT, MULTIPLIER_NORMAL, MULTIPLIER_HEAVY,
)

# Auto-fill with "Normal" mode for a 10 m³ helium envelope
mass = apply_fill_mode(10.0, "helium", FillMode.NORMAL)

# Manual fill clamped to burst-safe range
safe = apply_fill_mode(10.0, "helium", FillMode.MANUAL, manual_mass_kg=0.04)
```
"""

# ── Import physics constants ────────────────────────────────────────

from balloon_frontier.physics import (
    MOLAR_MASS,
    R,
    SEA_LEVEL_PRESSURE,
    SEA_LEVEL_TEMPERATURE,
)

# ── Public constants ─────────────────────────────────────────────────

# Fill level multipliers (relative to base optimal mass)
MULTIPLIER_LIGHT: float = 0.8   # 20% less gas — higher climb rate, shorter flight
MULTIPLIER_NORMAL: float = 1.0  # Baseline optimal fill
MULTIPLIER_HEAVY: float = 1.2   # 20% more gas — longer float, slower ascent
MULTIPLIER_AUTO: float = 1.0    # Auto = Normal (uses optimal baseline)

# Fill mode names mapped to multipliers
FILL_MODE_MULTIPLIERS = {
    "auto": MULTIPLIER_AUTO,
    "light": MULTIPLIER_LIGHT,
    "normal": MULTIPLIER_NORMAL,
    "heavy": MULTIPLIER_HEAVY,
}

# Safety factor: auto-fill masses never exceed this fraction of burst limit.
# 0.6 = auto-fill stays at 60% of the burst volume headroom.
BURST_SAFETY_FRACTION: float = 0.6

# ── Public enums ─────────────────────────────────────────────────

VALID_GAS_TYPES = list(MOLAR_MASS.keys())

# Convenience: preset volumes for known envelope types
ENVELOPE_VOLUMES = {
    "latex": 10.0,
    "mylar": 200.0,
    "zero_pressure": 300.0,
    "blimp": 500.0,
}


def calculate_optimal_fill(volume_m3: float, gas_type: str) -> float:
    """Calculate the optimal mass of lifting gas for an envelope.

    Computes the gas mass that exactly fills the envelope to its
    nominal volume at sea-level standard conditions (ideal gas law):

        mass = V · P · M / (R · T)

    Args:
        volume_m3: Nominal envelope volume in cubic metres (e.g. 10.0 for
                   a 10 m³ latex balloon).
        gas_type: Gas identifier. Must be one of:
                   `"helium"`, `"hydrogen"`, `"hot_air"`, `"methane"`.

    Returns:
        Optimal gas mass in kilograms at sea level.

    Raises:
        ValueError: If `gas_type` is not in the known gas enum.
    """
    if gas_type not in MOLAR_MASS:
        raise ValueError(
            f"Unknown gas type: {gas_type!r}. "
            f"Valid: {VALID_GAS_TYPES}"
        )

    M = MOLAR_MASS[gas_type]
    P = SEA_LEVEL_PRESSURE
    T = SEA_LEVEL_TEMPERATURE

    # Ideal gas law: V = nRT/P  →  mass = V·P·M / (R·T)
    mass = volume_m3 * P * M / (R * T)

    return round(mass, 6)


def get_fill_variants(volume_m3: float, gas_type: str) -> dict:
    """Return Light / Normal / Heavy fill masses for a given envelope."""
    base = calculate_optimal_fill(volume_m3, gas_type)
    return {
        "light": round(base * MULTIPLIER_LIGHT, 6),
        "normal": round(base * MULTIPLIER_NORMAL, 6),
        "heavy": round(base * MULTIPLIER_HEAVY, 6),
    }


def get_envelope_fill(env_id: str, gas_type: str) -> dict:
    """Get fill variants for a named envelope type.

    Args:
        env_id: Envelope identifier (e.g. `"latex"`, `"blimp"`).
        gas_type: Gas type string.

    Returns:
        Dict with `"base"`, `"light"`, `"normal"`, `"heavy"` masses.
    """
    volume = ENVELOPE_VOLUMES.get(env_id)
    if volume is None:
        raise ValueError(
            f"Unknown envelope: {env_id!r}. Valid: {list(ENVELOPE_VOLUMES.keys())}"
        )
    base = calculate_optimal_fill(volume, gas_type)
    return {
        "base": base,
        "light": round(base * MULTIPLIER_LIGHT, 6),
        "normal": round(base * MULTIPLIER_NORMAL, 6),
        "heavy": round(base * MULTIPLIER_HEAVY, 6),
    }


# ── Fill Mode Enum ──────────────────────────────────────────────

from enum import Enum, auto


class FillMode(Enum):
    """Fill mode for the launch state machine.

    AUTO, LIGHT, NORMAL, HEAVY use pre-calculated optimal masses.
    MANUAL lets the player specify an exact gas mass, optionally
    clamped to a burst-safe range.
    """
    AUTO   = auto()  # Auto-optimised fill (alias for NORMAL)
    LIGHT  = auto()  # 20% less gas — faster climb, shorter flight
    NORMAL = auto()  # Baseline optimal fill
    HEAVY  = auto()  # 20% more gas — longer float, slower ascent
    MANUAL = auto()  # Player-specified exact mass

    def get_multiplier(self) -> float:
        """Get the mass multiplier for this fill mode (all except MANUAL)."""
        if self == FillMode.MANUAL:
            raise ValueError("MANUAL mode requires an explicit mass")
        name = self.name.lower()
        return FILL_MODE_MULTIPLIERS.get(name, MULTIPLIER_NORMAL)

    def is_auto_mode(self) -> bool:
        """Return True for AUTO/LIGHT/NORMAL/HEAVY (preset modes)."""
        return self != FillMode.MANUAL


# ── Auto-fill integration ─────────────────────────────────────────

def get_auto_fill_mass(volume_m3: float, gas_type: str, mode: FillMode) -> float:
    """Calculate fill mass from an auto-fill mode (Light/Normal/Heavy/Auto).

    The returned mass is guaranteed to be burst-safe: it never exceeds
    the safe fraction of the burst volume limit.

    Args:
        volume_m3: Envelope nominal volume.
        gas_type: Gas type string.
        mode: Fill mode (AUTO, LIGHT, NORMAL, or HEAVY).

    Returns:
        Gas mass in kg, clamped to the burst-safe range.

    Raises:
        ValueError: If mode is MANUAL (use the explicit mass instead).
    """
    if mode == FillMode.MANUAL:
        raise ValueError("MANUAL mode requires an explicit mass")

    base = calculate_optimal_fill(volume_m3, gas_type)
    multiplier = mode.get_multiplier()
    raw_mass = base * multiplier

    # Clamp to burst-safe range.
    safe_max = calculate_max_safe_gas_mass(volume_m3, gas_type)
    return round(min(raw_mass, safe_max), 6)


def calculate_max_safe_gas_mass(volume_m3: float, gas_type: str) -> float:
    """Calculate the maximum gas mass that stays within the burst-safe zone.

    Uses the burst safety fraction (60% of optimal fill) so that even
    with thermal expansion during ascent, the balloon doesn't burst
    instantaneously.

    Args:
        volume_m3: Envelope nominal volume.
        gas_type: Gas type string.

    Returns:
        Maximum safe gas mass in kg.
    """
    base = calculate_optimal_fill(volume_m3, gas_type)
    return round(base * BURST_SAFETY_FRACTION, 6)


def get_fill_description(mode: FillMode) -> str:
    """Human-readable description for a fill mode."""
    descs = {
        FillMode.AUTO:   "Auto — optimal fill, safe burst margin",
        FillMode.LIGHT:  "Light — 20% less gas, faster climb",
        FillMode.NORMAL: "Normal — baseline optimal fill",
        FillMode.HEAVY:  "Heavy — 20% more gas, longer float",
        FillMode.MANUAL: "Manual — your choice",
    }
    return descs.get(mode, "Unknown fill mode")


def apply_fill_mode(volume_m3: float, gas_type: str, mode: FillMode, manual_mass_kg: float = None) -> float:
    """Apply a fill mode to get the final gas mass for the launch state machine.

    When mode is MANUAL, uses the provided `manual_mass_kg`.
    When mode is AUTO/LIGHT/NORMAL/HEAVY, calculates and clamps the mass.

    This is the single entry point the launch sequence should call to
    determine the gas mass before starting the simulation.

    Args:
        volume_m3: Envelope nominal volume.
        gas_type: Gas type string.
        mode: Selected fill mode.
        manual_mass_kg: Player-specified mass (only used when mode == MANUAL).

    Returns:
        Final gas mass in kg for the simulation state.
    """
    if mode == FillMode.MANUAL:
        if manual_mass_kg is None:
            # Fall back to safe auto-normal if the player hit "Manual" but didn't type a value
            return get_auto_fill_mass(volume_m3, gas_type, FillMode.NORMAL)
        # Clamp manual mass to burst-safe range
        safe_max = calculate_max_safe_gas_mass(volume_m3, gas_type)
        return round(min(max(manual_mass_kg, 0.001), safe_max), 6)
    else:
        return get_auto_fill_mass(volume_m3, gas_type, mode)
