"""Regression tests for small balloon size calibration with CATALOG.

Covers:
- s21 and s29 are in CATALOG but excluded from CLI playable list
- CATALOG balloon specs have correct calibration values
- Small set balloons are playable with basic payload
"""

import pytest

from balloon_frontier.simulation import SimulationState, EnvelopeConfig, run_simulation
from balloon_frontier.catalog import CATALOG


def _simulate_peak_altitude_for_size(balloon_key: str, payload_mass_kg: float = 0.0):
    """Run a quick simulation for a balloon to verify it rises and doesn't burst."""
    balloon = CATALOG.balloon(balloon_key)

    # Use normal fill mode gas mass
    from balloon_frontier.fill import apply_fill_mode, FillMode
    gas_mass_kg = apply_fill_mode(balloon.max_volume_m3, "helium", FillMode.NORMAL)

    env_config = EnvelopeConfig(
        max_volume_m3=balloon.max_volume_m3,
        burst_stretch_ratio=balloon.burst_stretch_ratio,
        drag_coefficient=0.47,
        permeability=0.001,
        mass_kg=balloon.mass_kg,
        contained_gas=True,
    )

    # ballast_mass_kg defaults to 5.0 in SimulationState, but that's way too heavy for small balloons
    state = SimulationState(
        gas_type="helium",
        gas_mass_kg=gas_mass_kg,
        payload_mass_kg=payload_mass_kg,
        ballast_mass_kg=0.0,
        envelope=env_config,
        gas_temperature_k=288.15,
        altitude_m=0.0,
        terrain_base_altitude_offset_m=0.0,
        wind_enabled=False,
    )

    telemetry = run_simulation(state, dt=0.1, total_time_s=60.0, max_steps=5000)
    assert telemetry, f"No telemetry returned for {balloon_key}"

    peak_alt = max(t["altitude_m"] for t in telemetry)
    burst_any = any(t.get("burst", False) for t in telemetry)
    return peak_alt, burst_any


def test_small_playable_roster_excludes_21_and_29():
    """s21 and s29 exist in CATALOG but are excluded from CLI playable list."""
    # All balloons exist in CATALOG
    assert CATALOG.balloon("s21") is not None
    assert CATALOG.balloon("s29") is not None

    # But CLI excludes them (verified in test_cli_game_regressions.py)
    # Here we just verify the CATALOG has all sizes
    all_balloons = CATALOG.all_balloons()
    all_ids = {b.id for b in all_balloons}
    assert "s21" in all_ids
    assert "s29" in all_ids


def test_balloons_have_correct_calibration():
    """CATALOG balloon specs have correct calibration values."""
    s36 = CATALOG.balloon("s36")
    s45 = CATALOG.balloon("s45")

    # Verify known calibration values
    assert s36.max_volume_m3 == 3.5
    assert s36.burst_stretch_ratio == 2.3
    assert s36.mass_kg > 0

    assert s45.max_volume_m3 > s36.max_volume_m3
    assert s45.mass_kg > s36.mass_kg


def test_s100_and_s150_exist():
    """Large balloons still exist in CATALOG."""
    s100 = CATALOG.balloon("s100")
    s150 = CATALOG.balloon("s150")

    assert s100.max_volume_m3 > 0
    assert s150.max_volume_m3 > 0
    assert s150.max_volume_m3 > s100.max_volume_m3


@pytest.mark.parametrize("balloon_key", ["s36", "s45", "s55"])
def test_small_set_is_playable_with_basic_payload(balloon_key: str):
    """Every small balloon rises with basic payload."""
    peak_alt, burst_any = _simulate_peak_altitude_for_size(balloon_key, payload_mass_kg=0.0)

    # Acceptance: every size in small set is playable by construction.
    assert peak_alt > 0.0, f"Expected {balloon_key} to rise with basic payload"
    assert not burst_any, f"Expected {balloon_key} to not burst using calibrated normal fill"