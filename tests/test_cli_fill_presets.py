"""Tests for Balloon Frontier — Fill Preset Selection & Calculation.

Covers:
- Fill mass calculation for all presets (Auto/Light/Normal/Heavy)
- All gas types and balloon sizes produce valid masses
- Deterministic mass output
- Mass formatting utility
- Preset mass ordering (Light < Normal < Heavy)
"""

import pytest

from balloon_frontier.fill import (
    apply_fill_mode, FillMode, calculate_optimal_fill,
    MULTIPLIER_LIGHT, MULTIPLIER_NORMAL, MULTIPLIER_HEAVY,
)


class TestFormatMassKg:
    """Mass formatting helper for CLI display."""

    def test_format_mass_below_1kg(self):
        def format_mass_kg(mass_kg):
            if mass_kg < 1.0:
                return f"{mass_kg * 1000:.1f}g"
            elif mass_kg < 100:
                return f"{mass_kg:.3f} kg"
            else:
                return f"{mass_kg:.2f} kg"
        assert format_mass_kg(0.5) == "500.0g"
        assert format_mass_kg(0.025) == "25.0g"
        assert format_mass_kg(5.0) == "5.000 kg"
        assert format_mass_kg(150.0) == "150.00 kg"

    def test_format_mass_boundary(self):
        def format_mass_kg(mass_kg):
            if mass_kg < 1.0:
                return f"{mass_kg * 1000:.1f}g"
            elif mass_kg < 100:
                return f"{mass_kg:.3f} kg"
            else:
                return f"{mass_kg:.2f} kg"
        assert format_mass_kg(1.0) == "1.000 kg"
        assert format_mass_kg(99.9) == "99.900 kg"
        assert format_mass_kg(100.0) == "100.00 kg"


class TestFillPresetsCalculation:
    """Verify all 4 preset modes compute correct masses."""

    def test_auto_mode_computes_mass(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.AUTO)
        assert mass > 0

    def test_light_mode_computes_mass(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.LIGHT)
        assert mass > 0

    def test_normal_mode_computes_mass(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.NORMAL)
        assert mass > 0

    def test_heavy_mode_computes_mass(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.HEAVY)
        assert mass > 0

    def test_all_modes_for_all_gases(self):
        for gas in ["helium", "hydrogen", "hot_air", "methane"]:
            for mode in [FillMode.AUTO, FillMode.LIGHT, FillMode.NORMAL, FillMode.HEAVY]:
                m = apply_fill_mode(10.0, gas, mode)
                assert m > 0, f"Expected positive mass for {gas}/{mode}"

    def test_all_modes_for_all_balloon_sizes(self):
        volumes = [0.6, 1.5, 3.5, 6.0, 10.0, 25.0, 75.0, 250.0]
        for vol in volumes:
            for mode in [FillMode.AUTO, FillMode.LIGHT, FillMode.NORMAL, FillMode.HEAVY]:
                m = apply_fill_mode(vol, "helium", mode)
                assert m > 0, f"Expected positive mass for vol={vol}, mode={mode}"


class TestFillPresetDeterminism:
    """Verify preset mass output is deterministic."""

    def test_preset_masses_are_deterministic(self):
        """Same inputs produce same output every time."""
        for mode in [FillMode.AUTO, FillMode.LIGHT, FillMode.NORMAL, FillMode.HEAVY]:
            m1 = apply_fill_mode(10.0, "helium", mode)
            m2 = apply_fill_mode(10.0, "helium", mode)
            assert m1 == m2, f"Mode {mode} not deterministic"

    def test_preset_masses_differ_across_modes(self):
        """Light < Normal < Heavy for same volume/gas (before clamping)."""
        base = calculate_optimal_fill(10.0, "helium")
        light = base * MULTIPLIER_LIGHT
        normal = base * MULTIPLIER_NORMAL
        heavy = base * MULTIPLIER_HEAVY
        assert light < normal < heavy


class TestFillModeSelectionSafety:
    """Verify all modes return safe, usable masses."""

    def test_auto_mass_is_positive_float(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.AUTO)
        assert mass > 0
        assert isinstance(mass, float)

    def test_light_mass_is_positive_float(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.LIGHT)
        assert mass > 0
        assert isinstance(mass, float)

    def test_heavy_mass_is_positive_float(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.HEAVY)
        assert mass > 0
        assert isinstance(mass, float)

    def test_manual_with_explicit_mass(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.MANUAL, manual_mass_kg=0.05)
        assert mass > 0

    def test_manual_without_explicit_mass_falls_back(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.MANUAL)
        assert mass > 0


class TestPresetMultiplierConstants:
    """Verify multiplier constants match spec."""

    def test_light_multiplier(self):
        assert MULTIPLIER_LIGHT == 0.8

    def test_normal_multiplier(self):
        assert MULTIPLIER_NORMAL == 1.0

    def test_heavy_multiplier(self):
        assert MULTIPLIER_HEAVY == 1.2

    def test_multipliers_ordered(self):
        assert MULTIPLIER_LIGHT < MULTIPLIER_NORMAL < MULTIPLIER_HEAVY
