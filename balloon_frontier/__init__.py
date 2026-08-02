"""Balloon Frontier - Package exports."""

from .physics import (
    G,
    R,
    R_AIR,
    SEA_LEVEL_PRESSURE,
    SEA_LEVEL_TEMPERATURE,
    MOLAR_MASS,
    atmosphere_temperature,
    atmosphere_pressure,
    atmosphere_density,
    gas_volume,
    gas_density,
    buoyant_force,
    drag_force,
    spherical_area,
    burst_volume,
)
from .fill import (
    calculate_optimal_fill,
    get_fill_variants,
    get_envelope_fill,
    ENVELOPE_VOLUMES,
    MULTIPLIER_LIGHT,
    MULTIPLIER_NORMAL,
    MULTIPLIER_HEAVY,
    FillMode,
    apply_fill_mode,
    get_auto_fill_mass,
    calculate_max_safe_gas_mass,
    get_fill_description,
    DEFAULT_BURST_STRETCH_RATIO,
    SAFE_FILL_PRESETS,
)
from .flight_score import calculate_flight_score
from .medal_tier import MedalTier, get_medal_tier, medal_tier_to_string

# Register lightweight tutorial components before either UI enumerates the catalog.
from .tutorial_catalog import ensure_tutorial_catalog as _ensure_tutorial_catalog

_ensure_tutorial_catalog()

# Use nominal launch volume for presets and clamp every fill below the
# envelope's configured burst-safe capacity.
from .preset_fill_guard import install_nominal_preset_fill as _install_nominal_preset_fill

_install_nominal_preset_fill()

# Keep near-ground terminal simulations from being described as ongoing climbs.
from .narrative_guard import install_narrative_guard as _install_narrative_guard

_install_narrative_guard()

# Real discord.Interaction objects may reject arbitrary custom attributes.
# Keep tutorial continuation state on application-owned objects and preserve
# completed reports when follow-up delivery fails.
from .discord_continuation_guard import (
    install_discord_continuation_guard as _install_discord_continuation_guard,
)

_install_discord_continuation_guard()

# Subdivide only numerically stiff horizontal-drag steps so quadratic drag
# approaches the wind velocity without sign-flipping into an overflow.
from .simulation_stability_guard import (
    install_simulation_stability_guard as _install_simulation_stability_guard,
)

_install_simulation_stability_guard()
