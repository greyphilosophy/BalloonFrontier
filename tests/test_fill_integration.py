"""Tests for Balloon Frontier — Auto-Fill Integration with Launch Sequence.

Verifies that the game launch flow correctly integrates fill.py's
auto-fill modes and burst-safe clamping.
"""

import pytest
from balloon_frontier.fill import (
    apply_fill_mode, calculate_max_safe_gas_mass, calculate_optimal_fill,
    FillMode,
)
from balloon_frontier.simulation import SimulationState, EnvelopeConfig, run_simulation


class TestAutoFillIntegration:
    """Test that auto-fill modes integrate correctly with launch."""

    def test_auto_mode_returns_safe_mass(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.AUTO)
        safe_max = calculate_max_safe_gas_mass(10.0, "helium")
        assert mass <= safe_max

    def test_light_mode_returns_safe_mass(self):
        light = apply_fill_mode(10.0, "helium", FillMode.LIGHT)
        auto = apply_fill_mode(10.0, "helium", FillMode.AUTO)
        assert light <= auto

    def test_heavy_mode_returns_safe_mass(self):
        heavy = apply_fill_mode(10.0, "helium", FillMode.HEAVY)
        safe_max = calculate_max_safe_gas_mass(10.0, "helium")
        assert heavy <= safe_max

    def test_normal_mode_returns_safe_mass(self):
        normal = apply_fill_mode(10.0, "helium", FillMode.NORMAL)
        safe_max = calculate_max_safe_gas_mass(10.0, "helium")
        assert normal <= safe_max

    def test_manual_mode_clamped_to_safe_max(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.MANUAL, manual_mass_kg=999.0)
        safe_max = calculate_max_safe_gas_mass(10.0, "helium")
        assert mass == safe_max

    def test_manual_mode_respects_small_mass(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.MANUAL, manual_mass_kg=0.04)
        assert mass == 0.04

    def test_all_modes_for_all_gas_types(self):
        for gas in ["helium", "hydrogen", "hot_air", "methane"]:
            for mode in [FillMode.AUTO, FillMode.LIGHT, FillMode.NORMAL, FillMode.HEAVY]:
                mass = apply_fill_mode(10.0, gas, mode)
                assert mass > 0
                assert mass <= calculate_max_safe_gas_mass(10.0, gas)


class TestBurstPrevention:
    """Test that burst threshold uses optimal mass as baseline."""

    def test_safe_max_uses_dynamic_formula(self):
        """With dynamic formula, safe_max = base * burst_stretch_ratio * SAFETY_MARGIN.

        For default burst_stretch_ratio=2.5 and SAFETY_MARGIN=0.6,
        safe_max = base * 1.5.
        """
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(10.0, "helium")
        expected = base * 2.5 * 0.6
        assert abs(safe - round(expected, 6)) < 0.0001

    def test_safe_max_custom_burst_stretch(self):
        """Different burst_stretch_ratio values yield different safe limits."""
        base = calculate_optimal_fill(10.0, "helium")
        safe_2x = calculate_max_safe_gas_mass(10.0, "helium", burst_stretch_ratio=2.0)
        safe_3x = calculate_max_safe_gas_mass(10.0, "helium", burst_stretch_ratio=3.0)
        assert safe_2x < safe_3x
        assert abs(safe_2x - round(base * 2.0 * 0.6, 6)) < 0.0001
        assert abs(safe_3x - round(base * 3.0 * 0.6, 6)) < 0.0001
    def test_safe_max_scales_linearly(self):
        s1 = calculate_max_safe_gas_mass(10.0, "helium")
        s2 = calculate_max_safe_gas_mass(20.0, "helium")
        assert abs(s2 / s1 - 2.0) < 0.01

    def test_auto_fill_never_causes_instant_burst(self):
        env_config = EnvelopeConfig(
            max_volume_m3=10.0,
            burst_stretch_ratio=3.0,
            contained_gas=True,
        )
        gas_mass = apply_fill_mode(10.0, "helium", FillMode.HEAVY)
        state = SimulationState(
            gas_type="helium",
            gas_mass_kg=gas_mass,
            payload_mass_kg=5.0,
            envelope=env_config,
        )
        tel = run_simulation(state, dt=0.1, total_time_s=1.0, max_steps=10)
        if tel:
            assert not tel[0]["burst"]


class TestFillModeLaunchFlow:
    """Integration test: simulate the game flow with fill modes."""

    def test_cli_flow_auto_fill(self):
        gas_mass = apply_fill_mode(10.0, "helium", FillMode.AUTO)
        assert gas_mass > 0

    def test_cli_flow_light_fill(self):
        gas_mass = apply_fill_mode(10.0, "helium", FillMode.LIGHT)
        assert gas_mass > 0

    def test_cli_flow_heavy_fill(self):
        gas_mass = apply_fill_mode(10.0, "helium", FillMode.HEAVY)
        assert gas_mass > 0

    def test_manual_fill_clamped(self):
        gas_mass = apply_fill_mode(10.0, "helium", FillMode.MANUAL, manual_mass_kg=99.0)
        safe_max = calculate_max_safe_gas_mass(10.0, "helium")
        assert gas_mass == safe_max

    def test_all_envelope_sizes_work(self):
        for env_vol in [0.5, 10.0, 100.0, 500.0]:
            for mode in [FillMode.AUTO, FillMode.LIGHT, FillMode.NORMAL, FillMode.HEAVY]:
                gas_mass = apply_fill_mode(env_vol, "helium", mode)
                assert gas_mass > 0
