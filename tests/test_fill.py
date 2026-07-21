"""Tests for Balloon Frontier — Optimal Gas Fill Calculator.

Covers:
- Base calculation correctness (ideal gas law)
- All gas types (helium, hydrogen, hot_air, methane)
- All envelope sizes (latex, mylar, zero_pressure, blimp)
- Light/Normal/Heavy multiplier derivation
- FillMode enum and apply_fill_mode integration
- Edge cases (zero volume, unknown gas)
- Deterministic / consistent returns
- Package-level exports
"""

import math
import pytest

from balloon_frontier.fill import (
    calculate_optimal_fill,
    get_fill_variants,
    get_auto_fill_mass,
    calculate_max_safe_gas_mass,
    get_fill_description,
    apply_fill_mode,
    FillMode,
    ENVELOPE_VOLUMES,
    MULTIPLIER_LIGHT,
    MULTIPLIER_NORMAL,
    MULTIPLIER_HEAVY,
    VALID_GAS_TYPES,
)
from balloon_frontier.physics import (
    R,
    SEA_LEVEL_PRESSURE,
    SEA_LEVEL_TEMPERATURE,
    MOLAR_MASS,
)


# ─── Constants ──────────────────────────────────────────────────────────

def test_multiplier_light():
    assert MULTIPLIER_LIGHT == 0.8

def test_multiplier_normal():
    assert MULTIPLIER_NORMAL == 1.0

def test_multiplier_heavy():
    assert MULTIPLIER_HEAVY == 1.2


# ─── Valid gas types ──────────────────────────────────────────────────

def test_valid_gas_types():
    assert set(VALID_GAS_TYPES) == {"helium", "hydrogen", "hot_air", "methane"}


# ─── Base calculation correctness ─────────────────────────────────────

class TestCalculateOptimalFill:
    """The core function must match the ideal gas law exactly."""

    def test_helium_10m3_is_positive(self):
        m = calculate_optimal_fill(10.0, "helium")
        assert m > 0

    def test_helium_10m3_matches_ideal_gas_law(self):
        """V=10, P=101325, T=288.15, M=0.0040026, R=8.314462618"""
        volume = 10.0
        M = MOLAR_MASS["helium"]
        expected = volume * SEA_LEVEL_PRESSURE * M / (R * SEA_LEVEL_TEMPERATURE)
        actual = calculate_optimal_fill(volume, "helium")
        assert abs(actual - expected) < 0.001

    def test_scales_linearly_with_volume(self):
        m1 = calculate_optimal_fill(10.0, "helium")
        m2 = calculate_optimal_fill(20.0, "helium")
        assert abs(m2 / m1 - 2.0) < 0.01

    def test_all_gas_types_positive(self):
        for gas in VALID_GAS_TYPES:
            m = calculate_optimal_fill(10.0, gas)
            assert m > 0, f"Expected positive mass for {gas}"

    def test_hydrogen_lighter_than_helium(self):
        m_h2 = calculate_optimal_fill(10.0, "hydrogen")
        m_he = calculate_optimal_fill(10.0, "helium")
        assert m_h2 < m_he

    def test_hot_air_heaviest_base(self):
        m_ha = calculate_optimal_fill(10.0, "hot_air")
        m_he = calculate_optimal_fill(10.0, "helium")
        assert m_ha > m_he

    def test_zero_volume_returns_zero(self):
        m = calculate_optimal_fill(0.0, "helium")
        assert abs(m) < 0.001

    def test_unknown_gas_raises(self):
        with pytest.raises(ValueError, match="Unknown gas"):
            calculate_optimal_fill(10.0, "nitrogen")

    def test_deterministic_repeated_calls(self):
        base = calculate_optimal_fill(500.0, "methane")
        for _ in range(20):
            assert calculate_optimal_fill(500.0, "methane") == base


# ─── Envelope volumes ──────────────────────────────────────────────

class TestEnvelopeVolumes:
    def test_all_volumes_defined(self):
        expected = {"latex", "mylar", "zero_pressure", "blimp"}
        assert set(ENVELOPE_VOLUMES.keys()) == expected

    def test_volumes_positive(self):
        for env_id, vol in ENVELOPE_VOLUMES.items():
            assert vol > 0, f"{env_id} volume should be > 0"

    def test_blimp_is_largest(self):
        blimp = ENVELOPE_VOLUMES["blimp"]
        latex = ENVELOPE_VOLUMES["latex"]
        assert blimp > latex


# ─── Fill variants ─────────────────────────────────────────────────────

class TestFillVariants:
    def test_returns_three_keys(self):
        v = get_fill_variants(10.0, "helium")
        assert set(v.keys()) == {"light", "normal", "heavy"}

    def test_light_is_08x_base(self):
        v = get_fill_variants(10.0, "helium")
        base = calculate_optimal_fill(10.0, "helium")
        assert abs(v["light"] - base * MULTIPLIER_LIGHT) < 0.001

    def test_normal_equals_base(self):
        v = get_fill_variants(10.0, "helium")
        base = calculate_optimal_fill(10.0, "helium")
        assert abs(v["normal"] - base * MULTIPLIER_NORMAL) < 0.001

    def test_heavy_is_12x_base(self):
        v = get_fill_variants(10.0, "helium")
        base = calculate_optimal_fill(10.0, "helium")
        assert abs(v["heavy"] - base * MULTIPLIER_HEAVY) < 0.001

    def test_light_less_than_heavy(self):
        v = get_fill_variants(300.0, "hydrogen")
        assert v["light"] < v["normal"] < v["heavy"]

    def test_variants_for_all_gases(self):
        for gas in VALID_GAS_TYPES:
            v = get_fill_variants(10.0, gas)
            assert v["light"] > 0
            assert v["normal"] > 0
            assert v["heavy"] > 0


# ─── FillMode enum ──────────────────────────────────────────────────

class TestFillMode:
    def test_has_all_modes(self):
        assert FillMode.AUTO is not None
        assert FillMode.LIGHT is not None
        assert FillMode.NORMAL is not None
        assert FillMode.HEAVY is not None
        assert FillMode.MANUAL is not None

    def test_auto_mode_get_multiplier(self):
        assert FillMode.AUTO.get_multiplier() == MULTIPLIER_NORMAL

    def test_light_mode_get_multiplier(self):
        assert FillMode.LIGHT.get_multiplier() == MULTIPLIER_LIGHT

    def test_heavy_mode_get_multiplier(self):
        assert FillMode.HEAVY.get_multiplier() == MULTIPLIER_HEAVY

    def test_manual_mode_raises(self):
        with pytest.raises(ValueError, match="MANUAL"):
            FillMode.MANUAL.get_multiplier()

    def test_is_auto_mode(self):
        assert FillMode.AUTO.is_auto_mode()
        assert FillMode.NORMAL.is_auto_mode()
        assert FillMode.MANUAL.is_auto_mode() is False

    def test_descriptions_exist(self):
        for mode in FillMode:
            desc = get_fill_description(mode)
            assert isinstance(desc, str)
            assert len(desc) > 3


# ─── Auto-fill integration ────────────────────────────────────────

class TestAutoFillIntegration:
    def test_apply_fill_mode_auto(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.AUTO)
        base = calculate_optimal_fill(10.0, "helium")
        assert mass > 0
        # Auto multiplier is 1.0, so mass equals base (not clamped by safe ceiling)
        assert mass == base

    def test_apply_fill_mode_light(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.LIGHT)
        assert mass > 0

    def test_apply_fill_mode_heavy(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.HEAVY)
        assert mass > 0

    def test_apply_fill_mode_manual_with_mass(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.MANUAL, manual_mass_kg=0.04)
        assert mass > 0

    def test_apply_fill_mode_manual_without_mass_falls_back(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.MANUAL)
        assert mass > 0

    def test_apply_fill_mode_clamps_manual_above_safe_max(self):
        safe = calculate_max_safe_gas_mass(10.0, "helium")
        mass = apply_fill_mode(10.0, "helium", FillMode.MANUAL, manual_mass_kg=999.0)
        assert mass == safe

    def test_manual_fill_clamped_with_custom_burst_stretch_ratio(self):
        """Verify manual fill is clamped to the burst-safe range derived from burst_stretch_ratio.

        This is the core safety invariant: a manual mass of 999 kg must never
        exceed the safe limit, regardless of what burst_stretch_ratio is used.
        """
        vol = 10.0
        gas = "helium"
        huge_mass = 999.0

        # Test with different burst_stretch_ratio values
        for ratio in [2.0, 2.5, 3.0, 4.0]:
            safe_max = calculate_max_safe_gas_mass(vol, gas, ratio)
            clamped = apply_fill_mode(vol, gas, FillMode.MANUAL,
                                     manual_mass_kg=huge_mass,
                                     burst_stretch_ratio=ratio)
            assert clamped == safe_max, (
                f"Manual mass should be clamped to safe_max for ratio={ratio}"
            )

    def test_manual_fill_clamped_with_balloon_burst_ratio(self):
        """Simulate the show_fill_presets() flow: manual mass routed through
        apply_fill_mode() with the balloon's burst stretch ratio.

        This test mirrors what happens in show_fill_presets() when the player
        selects Manual mode and enters a gas mass. The returned value must be
        clamped to the burst-safe range using the balloon's actual burst ratio.
        """
        # Simulate a typical balloon config (e.g., a 10m³ latex with burst=2.5)
        vol = 10.0
        gas = "helium"
        burst_ratio = 2.5

        # Player enters an enormous value (should be clamped)
        player_input = 50.0
        safe_max = calculate_max_safe_gas_mass(vol, gas, burst_ratio)
        result = apply_fill_mode(vol, gas, FillMode.MANUAL,
                                 manual_mass_kg=player_input,
                                 burst_stretch_ratio=burst_ratio)
        assert result == safe_max
        assert result < player_input, "Clamped value should be less than input"

    def test_manual_fill_respects_lower_bound(self):
        """Manual mass below the 0.001 kg floor should be clamped up."""
        result = apply_fill_mode(10.0, "helium", FillMode.MANUAL,
                                 manual_mass_kg=0.0001)
        assert result >= 0.001

    def test_manual_fill_within_safe_range_passes_through(self):
        """A reasonable manual mass within the safe range is returned as-is."""
        vol = 10.0
        gas = "helium"
        safe_max = calculate_max_safe_gas_mass(vol, gas)
        # Use half the safe max as a reasonable manual input
        manual = safe_max * 0.5
        result = apply_fill_mode(vol, gas, FillMode.MANUAL,
                                 manual_mass_kg=manual)
        assert result == round(manual, 6)

    def test_get_auto_fill_all_gases(self):
        for gas in VALID_GAS_TYPES:
            for mode in [FillMode.AUTO, FillMode.LIGHT, FillMode.NORMAL, FillMode.HEAVY]:
                m = get_auto_fill_mass(10.0, gas, mode)
                assert m > 0

    def test_safe_mass_above_optimal_with_dynamic_formula(self):
        """Dynamic formula makes safe_max > base, so presets aren't clamped."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(10.0, "helium")
        # safe = base * 2.5 * 0.6 = base * 1.5
        assert safe > base

    def test_dynamic_formula_calculation(self):
        """Verify the dynamic formula: safe = base * burst_stretch_ratio * SAFETY_MARGIN."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(10.0, "helium")
        expected = round(base * 2.5 * 0.6, 6)
        assert abs(safe - expected) < 0.0001

    def test_presets_yield_distinct_masses(self):
        """Light, Normal/Auto, and Heavy should produce different masses."""
        light = apply_fill_mode(10.0, "helium", FillMode.LIGHT)
        normal = apply_fill_mode(10.0, "helium", FillMode.NORMAL)
        heavy = apply_fill_mode(10.0, "helium", FillMode.HEAVY)
        auto = apply_fill_mode(10.0, "helium", FillMode.AUTO)
        # Auto = Normal
        assert auto == normal
        # Light < Normal < Heavy
        assert light < normal < heavy

    def test_different_burst_ratios_change_safe_ceiling(self):
        """Higher burst_stretch_ratio raises the safe ceiling."""
        safe_2 = calculate_max_safe_gas_mass(10.0, "helium", burst_stretch_ratio=2.0)
        safe_3 = calculate_max_safe_gas_mass(10.0, "helium", burst_stretch_ratio=3.0)
        assert safe_2 < safe_3

    def test_presets_unaffected_by_ceiling_when_below(self):
        """Preset masses shouldn't change when the ceiling is well above them."""
        volume = 10.0
        gas = "helium"
        for mode in [FillMode.LIGHT, FillMode.NORMAL]:
            m1 = apply_fill_mode(volume, gas, mode, burst_stretch_ratio=2.0)
            m2 = apply_fill_mode(volume, gas, mode, burst_stretch_ratio=3.0)
            assert m1 == m2


# ─── Package exports ─────────────────────────────────────────────

def test_package_exposes_calculate_optimal_fill():
    import balloon_frontier
    assert hasattr(balloon_frontier, "calculate_optimal_fill")

def test_package_exports_multipliers():
    import balloon_frontier
    assert hasattr(balloon_frontier, "MULTIPLIER_LIGHT")
    assert hasattr(balloon_frontier, "MULTIPLIER_NORMAL")
    assert hasattr(balloon_frontier, "MULTIPLIER_HEAVY")

def test_package_exposes_fill_mode():
    import balloon_frontier
    assert hasattr(balloon_frontier, "FillMode")
    assert hasattr(balloon_frontier, "ENVELOPE_VOLUMES")
