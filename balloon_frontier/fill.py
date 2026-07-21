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
MULTIPLIER_LIGHT: float = 0.8   # 20% less gas — less free lift, slower ascent, higher burst
MULTIPLIER_NORMAL: float = 1.0  # Baseline optimal fill
MULTIPLIER_HEAVY: float = 1.2   # 20% more gas — more free lift, faster ascent, earlier burst
MULTIPLIER_AUTO: float = 1.0    # Auto = Normal (uses optimal baseline)

# Fill mode names mapped to multipliers
FILL_MODE_MULTIPLIERS = {
    "auto": MULTIPLIER_AUTO,
    "light": MULTIPLIER_LIGHT,
    "normal": MULTIPLIER_NORMAL,
    "heavy": MULTIPLIER_HEAVY,
}

# Safety margin for dynamic burst-safe volume calculation.
# The safe fill mass is calculated as:
#   safe_volume = nominal_volume * burst_stretch_ratio * SAFETY_MARGIN
# A value of 0.6 means the safety limit sits at 60% of the burst volume,
# not 60% of the nominal volume. This allows Light/Normal/Heavy presets
# to produce distinct masses because the ceiling is much higher.
SAFETY_MARGIN: float = 0.6

# Default burst stretch ratio (used when the caller doesn't specify one)
DEFAULT_BURST_STRETCH_RATIO: float = 2.5

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
    LIGHT  = auto()  # 20% less gas — less free lift, slower ascent, higher burst
    NORMAL = auto()  # Baseline optimal fill
    HEAVY  = auto()  # 20% more gas — more free lift, faster ascent, earlier burst
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

def get_auto_fill_mass(
    volume_m3: float,
    gas_type: str,
    mode: FillMode,
    burst_stretch_ratio: float = DEFAULT_BURST_STRETCH_RATIO,
) -> float:
    """Calculate fill mass from an auto-fill mode (Light/Normal/Heavy/Auto).

    The returned mass is guaranteed to be burst-safe: it never exceeds
    the safe fraction of the burst volume limit.

    The safety limit uses a dynamic calculation based on the burst stretch ratio:
        safe_volume = nominal_volume * burst_stretch_ratio * SAFETY_MARGIN
        safe_mass = optimal_mass * burst_stretch_ratio * SAFETY_MARGIN

    This allows Light/Normal/Heavy/Auto presets to differentiate properly.

    Args:
        volume_m3: Envelope nominal volume.
        gas_type: Gas type string.
        mode: Fill mode (AUTO, LIGHT, NORMAL, or HEAVY).
        burst_stretch_ratio: Ratio of burst volume to nominal volume
            (e.g. 2.5 means the balloon can stretch to 250% before bursting).
            Defaults to DEFAULT_BURST_STRETCH_RATIO.

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

    # Clamp to burst-safe range (dynamic calculation).
    safe_max = calculate_max_safe_gas_mass(volume_m3, gas_type, burst_stretch_ratio)
    return round(min(raw_mass, safe_max), 6)


def calculate_max_safe_gas_mass(
    volume_m3: float,
    gas_type: str,
    burst_stretch_ratio: float = DEFAULT_BURST_STRETCH_RATIO,
) -> float:
    """Calculate the maximum gas mass that stays within the burst-safe zone.

    Uses the dynamic burst volume calculation:
        safe_volume = volume * burst_stretch_ratio * SAFETY_MARGIN
        safe_mass = optimal_mass * burst_stretch_ratio * SAFETY_MARGIN

    This means the safety limit is a fraction of the *burst volume*,
    not the nominal volume, so different presets can produce distinct
    masses.

    Args:
        volume_m3: Envelope nominal volume.
        gas_type: Gas type string.
        burst_stretch_ratio: Ratio of burst volume to nominal volume.
            Defaults to DEFAULT_BURST_STRETCH_RATIO.

    Returns:
        Maximum safe gas mass in kg.
    """
    base = calculate_optimal_fill(volume_m3, gas_type)
    return round(base * burst_stretch_ratio * SAFETY_MARGIN, 6)


def get_fill_description(mode: FillMode) -> str:
    """Human-readable description for a fill mode."""
    descs = {
        FillMode.AUTO:   "Auto — optimal fill, safe burst margin",
        FillMode.LIGHT:  "Light — less free lift, slower ascent, higher burst",
        FillMode.NORMAL: "Normal — baseline optimal fill",
        FillMode.HEAVY:  "Heavy — more free lift, faster ascent, earlier burst",
        FillMode.MANUAL: "Manual — your choice",
    }
    return descs.get(mode, "Unknown fill mode")


def apply_fill_mode(
    volume_m3: float,
    gas_type: str,
    mode: FillMode,
    manual_mass_kg: float = None,
    burst_stretch_ratio: float = DEFAULT_BURST_STRETCH_RATIO,
) -> float:
    """Apply a fill mode to get the final gas mass for the launch state machine.

    When mode is MANUAL, uses the provided `manual_mass_kg` clamped to the
    burst-safe range derived from `burst_stretch_ratio`.
    When mode is AUTO/LIGHT/NORMAL/HEAVY, calculates and clamps the mass.

    This is the single entry point the launch sequence should call to
    determine the gas mass before starting the simulation.

    Args:
        volume_m3: Envelope nominal volume.
        gas_type: Gas type string.
        mode: Selected fill mode.
        manual_mass_kg: Player-specified mass (only used when mode == MANUAL).
        burst_stretch_ratio: Ratio of burst volume to nominal volume.
            Defaults to DEFAULT_BURST_STRETCH_RATIO.

    Returns:
        Final gas mass in kg for the simulation state.
    """
    if mode == FillMode.MANUAL:
        if manual_mass_kg is None:
            # Fall back to safe auto-normal if the player hit "Manual" but didn't type a value
            return get_auto_fill_mass(volume_m3, gas_type, FillMode.NORMAL, burst_stretch_ratio)
        # Clamp manual mass to burst-safe range
        safe_max = calculate_max_safe_gas_mass(volume_m3, gas_type, burst_stretch_ratio)
        return round(min(max(manual_mass_kg, 0.001), safe_max), 6)
    else:
        return get_auto_fill_mass(volume_m3, gas_type, mode, burst_stretch_ratio)
