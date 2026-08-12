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

# Foundational aerostat components (ordinary air, lightweight heated envelope,
# and heater payloads) are registered before any transport builds its menus.
from .aerostat import register_aerostat_catalog_extensions as _register_aerostat_catalog_extensions

_register_aerostat_catalog_extensions()

from .preset_fill_guard import install_nominal_preset_fill as _install_nominal_preset_fill

_install_nominal_preset_fill()

from .narrative_guard import install_narrative_guard as _install_narrative_guard

_install_narrative_guard()

from .discord_continuation_guard import (
    install_discord_continuation_guard as _install_discord_continuation_guard,
)

_install_discord_continuation_guard()

from .simulation_stability_guard import (
    install_simulation_stability_guard as _install_simulation_stability_guard,
)

_install_simulation_stability_guard()

# This legacy-named guard now contains presentation-only protections. It does
# not substitute requests, weather, equipment, evaluators, or physics.
from .tutorial_report_guard import (
    install_tutorial_report_guard as _install_tutorial_report_guard,
)

_install_tutorial_report_guard()

# The installer name is retained for import compatibility; it now owns only the
# Story first-flight result split and Continue Story handoff.
from .tutorial_result_delivery import (
    install_tutorial_result_delivery as _install_tutorial_result_delivery,
)

_install_tutorial_result_delivery()
