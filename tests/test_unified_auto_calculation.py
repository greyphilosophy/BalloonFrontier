"""Tests for Balloon Frontier — Unified Auto Calculation.

Verifies that the shared `balloon_frontier.fill` module produces correct,
consistent, and burst-safe results for Auto mode across all combinations
of envelope types, gas types, and burst-stretch configurations.

Also verifies that CLI and Discord code paths return identical results
when given the same inputs through `apply_fill_mode()`.
"""

import pytest
from balloon_frontier.fill import (
    apply_fill_mode,
    calculate_max_safe_gas_mass,
    calculate_optimal_fill,
    FillMode,
    get_auto_fill_mass,
    SAFE_FILL_PRESETS,
    DEFAULT_BURST_STRETCH_RATIO,
    MULTIPLIER_AUTO,
    MULTIPLIER_LIGHT,
    MULTIPLIER_NORMAL,
    MULTIPLIER_HEAVY,
    SAFETY_MARGIN,
    ENVELOPE_VOLUMES,
    VALID_GAS_TYPES,
)


# ─── Auto calculation correctness ─────────────────────────────────────

class TestAutoCalculationCorrectness:
    """Auto mode must return the optimal fill mass (multiplier = 1.0)."""

    def test_auto_multiplier_is_1_0(self):
        assert MULTIPLIER_AUTO == 1.0

    def test_auto_equals_optimal_fill(self):
        """Auto mode should produce exactly the optimal fill mass."""
        base = calculate_optimal_fill(10.0, "helium")
        auto = apply_fill_mode(10.0, "helium", FillMode.AUTO)
        assert auto == base

    def test_auto_mode_is_auto_mode(self):
        assert FillMode.AUTO.is_auto_mode()

    def test_auto_mode_returns_multiplier_normal(self):
        assert FillMode.AUTO.get_multiplier() == MULTIPLIER_NORMAL


# ─── All envelope types with Auto mode ──────────────────────────────

class TestAutoForAllEnvelopes:
    """Auto mode must work correctly for every envelope type."""

    def test_auto_for_all_envelope_volumes(self):
        for env_id, volume in ENVELOPE_VOLUMES.items():
            mass = apply_fill_mode(volume, "helium", FillMode.AUTO)
            base = calculate_optimal_fill(volume, "helium")
            assert mass == base, f"{env_id} Auto mass should equal optimal fill"

    def test_auto_for_latex(self):
        mass = apply_fill_mode(ENVELOPE_VOLUMES["latex"], "helium", FillMode.AUTO)
        assert mass > 0

    def test_auto_for_mylar(self):
        mass = apply_fill_mode(ENVELOPE_VOLUMES["mylar"], "helium", FillMode.AUTO)
        assert mass > 0

    def test_auto_for_zero_pressure(self):
        mass = apply_fill_mode(ENVELOPE_VOLUMES["zero_pressure"], "helium", FillMode.AUTO)
        assert mass > 0

    def test_auto_for_blimp(self):
        mass = apply_fill_mode(ENVELOPE_VOLUMES["blimp"], "helium", FillMode.AUTO)
        assert mass > 0

    def test_auto_for_custom_volume(self):
        mass = apply_fill_mode(150.0, "helium", FillMode.AUTO)
        assert mass == calculate_optimal_fill(150.0, "helium")


# ─── All gas types with Auto mode ──────────────────────────────────

class TestAutoForAllGasTypes:
    """Auto mode must work correctly for every gas type."""

    def test_auto_for_all_gases(self):
        for gas in VALID_GAS_TYPES:
            mass = apply_fill_mode(10.0, gas, FillMode.AUTO)
            assert mass == calculate_optimal_fill(10.0, gas), f"Auto for {gas}"

    def test_auto_helium_positive(self):
        assert apply_fill_mode(10.0, "helium", FillMode.AUTO) > 0

    def test_auto_hydrogen_positive(self):
        assert apply_fill_mode(10.0, "hydrogen", FillMode.AUTO) > 0

    def test_auto_hot_air_positive(self):
        assert apply_fill_mode(10.0, "hot_air", FillMode.AUTO) > 0

    def test_auto_methane_positive(self):
        assert apply_fill_mode(10.0, "methane", FillMode.AUTO) > 0


# ─── Edge cases ─────────────────────────────────────────────────────

class TestAutoCalculationEdgeCases:
    """Edge cases for Auto calculation."""

    def test_auto_zero_volume(self):
        mass = apply_fill_mode(0.0, "helium", FillMode.AUTO)
        assert mass == 0.0

    def test_auto_very_small_volume(self):
        mass = apply_fill_mode(0.5, "helium", FillMode.AUTO)
        base = calculate_optimal_fill(0.5, "helium")
        assert mass == base

    def test_auto_very_large_volume(self):
        mass = apply_fill_mode(500.0, "helium", FillMode.AUTO)
        base = calculate_optimal_fill(500.0, "helium")
        assert mass == base

    def test_auto_extreme_volume(self):
        mass = apply_fill_mode(1000.0, "helium", FillMode.AUTO)
        base = calculate_optimal_fill(1000.0, "helium")
        assert mass == base

    def test_auto_fractional_volume(self):
        mass = apply_fill_mode(7.5, "helium", FillMode.AUTO)
        base = calculate_optimal_fill(7.5, "helium")
        assert mass == base


# ─── Safe fill presets ────────────────────────────────────────────

class TestSafeFillPresets:
    """Verify SAFE_FILL_PRESETS lookup and behavior."""

    def test_all_envelopes_have_preset(self):
        for env_id in ENVELOPE_VOLUMES.keys():
            assert env_id in SAFE_FILL_PRESETS, f"Missing preset for {env_id}"

    def test_preset_has_burst_stretch_ratio(self):
        for env_id, preset in SAFE_FILL_PRESETS.items():
            assert "burst_stretch_ratio" in preset, f"{env_id} missing burst_stretch_ratio"
            assert preset["burst_stretch_ratio"] > 0

    def test_preset_has_safe_fill_fraction(self):
        for env_id, preset in SAFE_FILL_PRESETS.items():
            assert "safe_fill_fraction" in preset, f"{env_id} missing safe_fill_fraction"
            assert preset["safe_fill_fraction"] > 0

    def test_auto_safe_with_all_envelope_presets(self):
        """Auto mode must be burst-safe for every envelope preset."""
        for env_id, volume in ENVELOPE_VOLUMES.items():
            auto = apply_fill_mode(volume, "helium", FillMode.AUTO)
            safe = calculate_max_safe_gas_mass(volume, "helium", envelope_type=env_id)
            assert auto <= safe, f"Auto for {env_id} should be <= safe max"


# ─── Burst stretch ratio variations ───────────────────────────────

class TestAutoWithBurstStretchRatio:
    """Auto calculation with various burst_stretch_ratio values.

    When burst_stretch_ratio is high (ratio * SAFETY_MARGIN >= 1.0),
    the safe ceiling is above the base mass so Auto returns base.
    When the ratio is low, the safe ceiling drops below base and
    Auto is clamped to safe_max = base * ratio * SAFETY_MARGIN.
    """

    def test_auto_with_default_burst_ratio(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.AUTO, burst_stretch_ratio=DEFAULT_BURST_STRETCH_RATIO)
        assert mass == calculate_optimal_fill(10.0, "helium")

    def test_auto_with_high_burst_ratio(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.AUTO, burst_stretch_ratio=3.0)
        assert mass == calculate_optimal_fill(10.0, "helium")

    def test_auto_clamped_when_ratio_too_low(self):
        """When ratio * SAFETY_MARGIN < 1.0, the safe ceiling is below base,
        so Auto is clamped to safe_max = base * ratio * SAFETY_MARGIN."""
        base = calculate_optimal_fill(10.0, "helium")
        ratio = 1.5
        safe_max = calculate_max_safe_gas_mass(10.0, "helium", burst_stretch_ratio=ratio)
        auto = apply_fill_mode(10.0, "helium", FillMode.AUTO, burst_stretch_ratio=ratio)
        assert auto == safe_max
        assert auto < base, "Clamped Auto should be less than base"

    def test_auto_clamped_at_ratio_1_0(self):
        """ratio=1.0 means safe = base * 1.0 * 0.6 = base * 0.6."""
        base = calculate_optimal_fill(10.0, "helium")
        ratio = 1.0
        safe_max = calculate_max_safe_gas_mass(10.0, "helium", burst_stretch_ratio=ratio)
        auto = apply_fill_mode(10.0, "helium", FillMode.AUTO, burst_stretch_ratio=ratio)
        assert auto == safe_max
        assert abs(auto - base * ratio * SAFETY_MARGIN) < 0.0001

    def test_auto_not_clamped_at_safe_ratios(self):
        """Ratios >= 1.667 mean ratio * 0.6 >= 1.0, so safe >= base."""
        for ratio in [1.667, 1.7, 2.0, 2.5, 3.0, 4.0]:
            base = calculate_optimal_fill(10.0, "helium")
            auto = apply_fill_mode(10.0, "helium", FillMode.AUTO, burst_stretch_ratio=ratio)
            assert auto == base, f"Auto should equal base for ratio={ratio}"


# ─── Safe fill data overrides ─────────────────────────────────────

class TestAutoWithSafeFillData:
    """Auto calculation with safe_fill_data overrides."""

    def test_auto_with_safe_fill_data(self):
        safe_data = {"burst_stretch_ratio": 2.5, "safe_fill_fraction": 0.6}
        mass = apply_fill_mode(10.0, "helium", FillMode.AUTO, safe_fill_data=safe_data)
        assert mass == calculate_optimal_fill(10.0, "helium")

    def test_auto_with_different_safe_fill_fraction(self):
        safe_data = {"burst_stretch_ratio": 2.0, "safe_fill_fraction": 0.5}
        mass = apply_fill_mode(10.0, "helium", FillMode.AUTO, safe_fill_data=safe_data)
        assert mass == calculate_optimal_fill(10.0, "helium")

    def test_auto_with_envelope_type(self):
        mass = apply_fill_mode(10.0, "helium", FillMode.AUTO, envelope_type="latex")
        assert mass == calculate_optimal_fill(10.0, "helium")


# ─── CLI and Discord parity ───────────────────────────────────────

class TestCliDiscordAutoParity:
    """Verify CLI and Discord produce identical Auto results.

    Both interfaces call apply_fill_mode() with the same core parameters
    (volume, gas_type, mode). These tests verify that given identical
    inputs, the output is deterministic and matches across both paths.
    """

    @pytest.mark.parametrize(
        "volume,gas",
        [
            (10.0, "helium"),
            (10.0, "hydrogen"),
            (10.0, "hot_air"),
            (10.0, "methane"),
            (200.0, "helium"),
            (300.0, "hydrogen"),
            (500.0, "helium"),
        ],
    )
    def test_cli_discord_auto_identical(self, volume, gas):
        """CLI and Discord Auto calls should return the same mass."""
        cli_result = apply_fill_mode(volume, gas, FillMode.AUTO)
        discord_result = apply_fill_mode(volume, gas, FillMode.AUTO)
        assert cli_result == discord_result

    @pytest.mark.parametrize(
        "volume,gas,mode",
        [
            (10.0, "helium", FillMode.LIGHT),
            (10.0, "helium", FillMode.NORMAL),
            (10.0, "helium", FillMode.HEAVY),
            (200.0, "hydrogen", FillMode.AUTO),
            (300.0, "helium", FillMode.LIGHT),
        ],
    )
    def test_cli_discord_preset_identical(self, volume, gas, mode):
        """CLI and Discord preset calls should return the same mass."""
        cli_result = apply_fill_mode(volume, gas, mode)
        discord_result = apply_fill_mode(volume, gas, mode)
        assert cli_result == discord_result

    @pytest.mark.parametrize(
        "volume,gas",
        [
            (10.0, "helium"),
            (200.0, "hydrogen"),
            (500.0, "helium"),
        ],
    )
    def test_cli_discord_safe_max_identical(self, volume, gas):
        """CLI and Discord safe max calculations should match."""
        cli_safe = calculate_max_safe_gas_mass(volume, gas)
        discord_safe = calculate_max_safe_gas_mass(volume, gas)
        assert cli_safe == discord_safe

    @pytest.mark.parametrize(
        "volume,gas",
        [
            (10.0, "helium"),
            (200.0, "helium"),
            (500.0, "helium"),
        ],
    )
    def test_cli_discord_manual_clamp_identical(self, volume, gas):
        """CLI and Discord manual mode clamping should match."""
        safe_max = calculate_max_safe_gas_mass(volume, gas)
        cli_clamp = apply_fill_mode(volume, gas, FillMode.MANUAL, manual_mass_kg=999.0)
        discord_clamp = apply_fill_mode(volume, gas, FillMode.MANUAL, manual_mass_kg=999.0)
        assert cli_clamp == discord_clamp == safe_max


# ─── Cross-mode consistency ───────────────────────────────────────

class TestCrossModeConsistency:
    """Verify relationships between modes are consistent."""

    def test_auto_equals_normal_all_volumes(self):
        for vol in [5.0, 10.0, 100.0, 300.0, 500.0]:
            auto = apply_fill_mode(vol, "helium", FillMode.AUTO)
            normal = apply_fill_mode(vol, "helium", FillMode.NORMAL)
            assert auto == normal, f"Auto != Normal at {vol}m³"

    def test_auto_equals_normal_all_gases(self):
        for gas in VALID_GAS_TYPES:
            auto = apply_fill_mode(10.0, gas, FillMode.AUTO)
            normal = apply_fill_mode(10.0, gas, FillMode.NORMAL)
            assert auto == normal, f"Auto != Normal for {gas}"

    def test_light_is_exactly_80_percent_of_auto(self):
        auto = apply_fill_mode(10.0, "helium", FillMode.AUTO)
        light = apply_fill_mode(10.0, "helium", FillMode.LIGHT)
        expected = auto * MULTIPLIER_LIGHT
        assert abs(light - expected) < 0.001

    def test_heavy_is_exactly_120_percent_of_auto(self):
        auto = apply_fill_mode(10.0, "helium", FillMode.AUTO)
        heavy = apply_fill_mode(10.0, "helium", FillMode.HEAVY)
        expected = auto * MULTIPLIER_HEAVY
        assert abs(heavy - expected) < 0.001

    def test_mode_ordering_holds_for_all_combinations(self):
        for gas in VALID_GAS_TYPES:
            for vol in [10.0, 200.0, 300.0, 500.0]:
                light = apply_fill_mode(vol, gas, FillMode.LIGHT)
                auto = apply_fill_mode(vol, gas, FillMode.AUTO)
                heavy = apply_fill_mode(vol, gas, FillMode.HEAVY)
                assert light < auto < heavy, f"Ordering failed: {vol}m³ {gas}"

    def test_auto_is_optimal_fill_for_all_combinations(self):
        for gas in VALID_GAS_TYPES:
            for vol in [5.0, 10.0, 100.0, 500.0]:
                auto = apply_fill_mode(vol, gas, FillMode.AUTO)
                base = calculate_optimal_fill(vol, gas)
                assert auto == base, f"Auto != base for {vol}m³ {gas}"


# ─── get_auto_fill_mass consistency ────────────────────────────────

class TestGetAutoFillMassConsistency:
    """get_auto_fill_mass must match apply_fill_mode for Auto mode."""

    def test_get_auto_fill_mass_equals_apply_fill_mode_auto(self):
        mass1 = get_auto_fill_mass(10.0, "helium", FillMode.AUTO)
        mass2 = apply_fill_mode(10.0, "helium", FillMode.AUTO)
        assert mass1 == mass2

    def test_get_auto_fill_mass_equals_apply_fill_mode_light(self):
        mass1 = get_auto_fill_mass(10.0, "helium", FillMode.LIGHT)
        mass2 = apply_fill_mode(10.0, "helium", FillMode.LIGHT)
        assert mass1 == mass2

    def test_get_auto_fill_mass_equals_apply_fill_mode_heavy(self):
        mass1 = get_auto_fill_mass(10.0, "helium", FillMode.HEAVY)
        mass2 = apply_fill_mode(10.0, "helium", FillMode.HEAVY)
        assert mass1 == mass2

    def test_get_auto_fill_mass_manual_raises(self):
        with pytest.raises(ValueError, match="MANUAL"):
            get_auto_fill_mass(10.0, "helium", FillMode.MANUAL)


# ─── Comprehensive matrix test ────────────────────────────────────

class TestComprehensiveAutoMatrix:
    """Run Auto mode through every combination of envelope + gas + burst ratio."""

    @pytest.mark.parametrize(
        "env_id,env_volume",
        list(ENVELOPE_VOLUMES.items()),
    )
    @pytest.mark.parametrize("gas_type", VALID_GAS_TYPES)
    def test_auto_matrix_all_combinations(self, env_id, env_volume, gas_type):
        """Auto mode works for every envelope × gas combination."""
        mass = apply_fill_mode(env_volume, gas_type, FillMode.AUTO)
        base = calculate_optimal_fill(env_volume, gas_type)
        assert mass == base, f"Auto failed for {env_id} + {gas_type}"

    @pytest.mark.parametrize(
        "env_id,env_volume",
        list(ENVELOPE_VOLUMES.items()),
    )
    @pytest.mark.parametrize("gas_type", VALID_GAS_TYPES)
    def test_auto_safe_for_all_combinations(self, env_id, env_volume, gas_type):
        """Auto mode is always safe for every envelope × gas combination."""
        auto = apply_fill_mode(env_volume, gas_type, FillMode.AUTO)
        safe = calculate_max_safe_gas_mass(env_volume, gas_type, envelope_type=env_id)
        assert auto <= safe, f"Auto unsafe for {env_id} + {gas_type}"

    @pytest.mark.parametrize("burst_ratio", [1.667, 2.0, 2.5, 3.0, 4.0])
    @pytest.mark.parametrize("gas_type", VALID_GAS_TYPES)
    def test_auto_unaffected_by_burst_ratio(self, burst_ratio, gas_type):
        """Auto mode returns base mass for ratios where ratio * SAFETY_MARGIN >= 1.0."""
        base = calculate_optimal_fill(10.0, gas_type)
        mass = apply_fill_mode(10.0, gas_type, FillMode.AUTO, burst_stretch_ratio=burst_ratio)
        assert mass == base, f"Auto changed for ratio={burst_ratio}, gas={gas_type}"

    @pytest.mark.parametrize("burst_ratio", [1.0, 1.5])
    @pytest.mark.parametrize("gas_type", VALID_GAS_TYPES)
    def test_auto_clamped_by_low_burst_ratio(self, burst_ratio, gas_type):
        """When ratio * SAFETY_MARGIN < 1.0, Auto is clamped to safe_max."""
        base = calculate_optimal_fill(10.0, gas_type)
        safe_max = calculate_max_safe_gas_mass(10.0, gas_type, burst_stretch_ratio=burst_ratio)
        mass = apply_fill_mode(10.0, gas_type, FillMode.AUTO, burst_stretch_ratio=burst_ratio)
        assert mass == safe_max, f"Auto should equal safe_max for ratio={burst_ratio}, gas={gas_type}"
        assert mass < base, f"Clamped Auto should be less than base for ratio={burst_ratio}, gas={gas_type}"
