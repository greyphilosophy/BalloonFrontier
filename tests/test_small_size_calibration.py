import pytest

import cli_game
from balloon_frontier.simulation import SimulationState, EnvelopeConfig, run_simulation


def _simulate_peak_altitude_for_size(balloon_key: str, payload_mass_kg: float = 1.0):
    spec = cli_game.BALLOON_SIZES[balloon_key]
    gas_mass_kg = spec["fill_g"][1] / 1000.0

    env_config = EnvelopeConfig(
        max_volume_m3=spec["max_vol"],
        burst_stretch_ratio=spec["burst"],
        drag_coefficient=0.47,
        permeability=0.001,
        mass_kg=spec["mass_kg"],
        contained_gas=True,
    )

    state = SimulationState(
        gas_type="helium",
        gas_mass_kg=gas_mass_kg,
        payload_mass_kg=payload_mass_kg,
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
    assert "s21" in cli_game.BALLOON_SIZES
    assert "s29" in cli_game.BALLOON_SIZES

    assert "s21" not in cli_game.PLAYABLE_BALLOON_LIST
    assert "s29" not in cli_game.PLAYABLE_BALLOON_LIST

    assert cli_game.BALLOON_LIST == cli_game.PLAYABLE_BALLOON_LIST


def test_fill_g_calibration_updated_for_s36_and_s45_only():
    assert cli_game.BALLOON_SIZES["s36"]["fill_g"] == (30, 1158)
    assert cli_game.BALLOON_SIZES["s45"]["fill_g"] == (50, 1163)

    # Must remain unchanged per acceptance criteria
    assert cli_game.BALLOON_SIZES["s100"]["fill_g"] == (400, 7000)
    assert cli_game.BALLOON_SIZES["s150"]["fill_g"] == (1000, 15000)


@pytest.mark.parametrize("balloon_key", ["s36", "s45", "s55"])
def test_small_set_is_playable_with_basic_payload(balloon_key: str):
    peak_alt, burst_any = _simulate_peak_altitude_for_size(balloon_key, payload_mass_kg=cli_game.PAYLOADS["none"][1])

    # Acceptance: every size in small set is playable by construction.
    assert peak_alt > 0.0, f"Expected {balloon_key} to rise with basic payload"
    assert not burst_any, f"Expected {balloon_key} to not burst using calibrated manual safe max gas mass"
