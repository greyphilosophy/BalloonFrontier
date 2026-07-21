"""Tests for Balloon Frontier — calculate_max_safe_gas_mass.

Covers:
- Dynamic formula correctness (base * ratio * fraction)
- Envelope type presets (latex, mylar, zero_pressure, blimp)
- Contained vs zero-pressure envelope comparisons
- Safety margin comparison (old 60% rule vs new dynamic formula)
- Parameter priority resolution (safe_fill_data > explicit arg > preset > default)
- Edge cases (missing parameters, unknown envelope, zero volume, all gases)
- Safe_fill_data partial overrides
"""

import pytest

from balloon_frontier.fill import (
    calculate_max_safe_gas_mass,
    calculate_optimal_fill,
    DEFAULT_BURST_STRETCH_RATIO,
    SAFETY_MARGIN,
    SAFE_FILL_PRESETS,
    ENVELOPE_VOLUMES,
    VALID_GAS_TYPES,
)


# ─── Dynamic formula correctness ────────────────────────────────────

class TestDynamicFormula:
    """The core safety formula: safe = base * ratio * fraction."""

    def test_formula_matches_ideal_gas_law_base(self):
        """Safe mass is derived from the ideal gas law base."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(10.0, "helium")
        expected = round(base * DEFAULT_BURST_STRETCH_RATIO * SAFETY_MARGIN, 6)
        assert abs(safe - expected) < 0.0001

    def test_safe_mass_is_always_positive(self):
        """Safe mass should be positive for any valid input."""
        for gas in VALID_GAS_TYPES:
            safe = calculate_max_safe_gas_mass(10.0, gas)
            assert safe > 0, f"Safe mass for {gas} should be positive"

    def test_safe_mass_scales_with_volume(self):
        """Safe mass should scale linearly with volume."""
        safe_10 = calculate_max_safe_gas_mass(10.0, "helium")
        safe_20 = calculate_max_safe_gas_mass(20.0, "helium")
        ratio = safe_20 / safe_10
        assert abs(ratio - 2.0) < 0.01

    def test_zero_volume_returns_zero(self):
        safe = calculate_max_safe_gas_mass(0.0, "helium")
        assert abs(safe) < 0.001

    def test_all_gas_types_produce_safe_mass(self):
        for gas in VALID_GAS_TYPES:
            safe = calculate_max_safe_gas_mass(10.0, gas)
            assert safe > 0, f"Expected positive safe mass for {gas}"

    def test_formula_with_explicit_parameters(self):
        """When all parameters are explicit, formula is straightforward."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(
            10.0, "helium",
            burst_stretch_ratio=2.5,
            safe_fill_data={"safe_fill_fraction": 0.6},
        )
        expected = round(base * 2.5 * 0.6, 6)
        assert abs(safe - expected) < 0.0001


# ─── Envelope type presets ────────────────────────────────────────

class TestEnvelopeTypePresets:
    """Each envelope type gets correct ratio + fraction from SAFE_FILL_PRESETS."""

    def test_latex_uses_preset(self):
        """Latex should use ratio=2.5, fraction=0.6."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(10.0, "helium", envelope_type="latex")
        expected = round(base * 2.5 * 0.6, 6)
        assert abs(safe - expected) < 0.0001

    def test_mylar_uses_preset(self):
        """Mylar should use ratio=3.0, fraction=0.55."""
        base = calculate_optimal_fill(200.0, "helium")
        safe = calculate_max_safe_gas_mass(200.0, "helium", envelope_type="mylar")
        expected = round(base * 3.0 * 0.55, 6)
        assert abs(safe - expected) < 0.0001

    def test_zero_pressure_uses_preset(self):
        """Zero-pressure should use ratio=1.8, fraction=0.65."""
        base = calculate_optimal_fill(300.0, "helium")
        safe = calculate_max_safe_gas_mass(300.0, "helium", envelope_type="zero_pressure")
        expected = round(base * 1.8 * 0.65, 6)
        assert abs(safe - expected) < 0.0001

    def test_blimp_uses_preset(self):
        """Blimp should use ratio=2.0, fraction=0.6."""
        base = calculate_optimal_fill(500.0, "helium")
        safe = calculate_max_safe_gas_mass(500.0, "helium", envelope_type="blimp")
        expected = round(base * 2.0 * 0.6, 6)
        assert abs(safe - expected) < 0.0001

    def test_all_envelope_types_produce_safe_mass(self):
        """Every envelope type should produce a positive safe mass."""
        for env_id, volume in ENVELOPE_VOLUMES.items():
            safe = calculate_max_safe_gas_mass(volume, "helium", envelope_type=env_id)
            assert safe > 0, f"Safe mass for {env_id} should be positive"

    def test_case_insensitive_envelope_type(self):
        """Envelope type lookup should be case-insensitive."""
        safe_lower = calculate_max_safe_gas_mass(10.0, "helium", envelope_type="latex")
        safe_upper = calculate_max_safe_gas_mass(10.0, "helium", envelope_type="LATEX")
        safe_mixed = calculate_max_safe_gas_mass(10.0, "helium", envelope_type="LaTeX")
        assert safe_lower == safe_upper == safe_mixed


# ─── Contained vs zero-pressure comparison ────────────────────────

class TestContainedVsZeroPressure:
    """Compare safety margins between contained and zero-pressure envelopes."""

    def test_contained_has_higher_burst_ratio_than_zero_pressure(self):
        """Contained envelopes (latex, mylar) stretch more than zero-pressure."""
        latex_preset = SAFE_FILL_PRESETS["latex"]
        zp_preset = SAFE_FILL_PRESETS["zero_pressure"]
        assert latex_preset["burst_stretch_ratio"] > zp_preset["burst_stretch_ratio"]

    def test_zero_pressure_has_higher_safe_fraction(self):
        """Zero-pressure envelopes use a higher safe_fill_fraction (0.65 vs ~0.6)."""
        zp_frac = SAFE_FILL_PRESETS["zero_pressure"]["safe_fill_fraction"]
        latex_frac = SAFE_FILL_PRESETS["latex"]["safe_fill_fraction"]
        assert zp_frac > latex_frac

    def test_contained_safe_mass_exceeds_zero_pressure_per_unit_volume(self):
        """Per unit volume, contained envelopes can carry more safe gas mass."""
        base = calculate_optimal_fill(1.0, "helium")
        safe_contained = base * SAFE_FILL_PRESETS["latex"]["burst_stretch_ratio"] * \
                         SAFE_FILL_PRESETS["latex"]["safe_fill_fraction"]
        safe_zp = base * SAFE_FILL_PRESETS["zero_pressure"]["burst_stretch_ratio"] * \
                  SAFE_FILL_PRESETS["zero_pressure"]["safe_fill_fraction"]
        # latex: 2.5 * 0.6 = 1.5; zero_pressure: 1.8 * 0.65 = 1.17
        assert safe_contained > safe_zp


# ─── Safety margin comparison (old 60% rule vs new) ──────────────

class TestOldVsNewSafetyMargin:
    """Compare the old flat 60% rule against the new dynamic formula."""

    def test_new_safety_margin_exceeds_old_rule(self):
        """Old rule: safe = base * 0.6. New: safe = base * ratio * fraction.
        With default ratio=2.5 and fraction=0.6, new = base * 1.5 (2.5x the old)."""
        base = calculate_optimal_fill(10.0, "helium")
        old_safe = base * 0.6
        new_safe = calculate_max_safe_gas_mass(10.0, "helium")
        assert new_safe > old_safe
        # The new limit should be exactly 2.5x the old limit
        expected_multiplier = DEFAULT_BURST_STRETCH_RATIO
        assert abs(new_safe / old_safe - expected_multiplier) < 0.01

    def test_old_rule_was_too_restrictive(self):
        """Old 60% of nominal volume was much lower than burst volume."""
        base = calculate_optimal_fill(10.0, "helium")
        old_safe = base * 0.6
        burst_mass = base * DEFAULT_BURST_STRETCH_RATIO
        # Old safe was only 24% of burst mass (0.6 / 2.5 = 0.24)
        assert old_safe / burst_mass < 0.3

    def test_new_rule_properly_targets_burst_volume(self):
        """New rule: safe = burst_volume * 0.6 = nominal * ratio * 0.6."""
        base = calculate_optimal_fill(10.0, "helium")
        burst_mass = base * DEFAULT_BURST_STRETCH_RATIO
        new_safe = calculate_max_safe_gas_mass(10.0, "helium")
        # New safe should be 60% of burst mass
        assert abs(new_safe / burst_mass - SAFETY_MARGIN) < 0.01

    def test_new_rule_raises_ceiling_above_optimal(self):
        """The new safe ceiling sits above the base optimal mass, so
        Light/Normal/Heavy presets are no longer clamped."""
        base = calculate_optimal_fill(10.0, "helium")
        new_safe = calculate_max_safe_gas_mass(10.0, "helium")
        assert new_safe > base


# ─── Parameter priority resolution ────────────────────────────────

class TestParameterPriority:
    """Priority: safe_fill_data > explicit arg > preset > default."""

    def test_safe_fill_data_overrides_explicit_burst_ratio(self):
        """When safe_fill_data has burst_stretch_ratio, it overrides the explicit arg."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(
            10.0, "helium",
            burst_stretch_ratio=2.0,
            safe_fill_data={"burst_stretch_ratio": 3.0},
        )
        expected = round(base * 3.0 * SAFETY_MARGIN, 6)
        assert abs(safe - expected) < 0.0001

    def test_safe_fill_data_only_fraction_uses_explicit_ratio(self):
        """safe_fill_data with only fraction -> ratio from explicit arg."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(
            10.0, "helium",
            burst_stretch_ratio=3.0,
            safe_fill_data={"safe_fill_fraction": 0.5},
        )
        expected = round(base * 3.0 * 0.5, 6)
        assert abs(safe - expected) < 0.0001

    def test_safe_fill_data_only_ratio_uses_default_fraction(self):
        """safe_fill_data with only ratio -> fraction from SAFETY_MARGIN."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(
            10.0, "helium",
            safe_fill_data={"burst_stretch_ratio": 2.0},
        )
        expected = round(base * 2.0 * SAFETY_MARGIN, 6)
        assert abs(safe - expected) < 0.0001

    def test_explicit_burst_ratio_overrides_preset(self):
        """Explicit burst_stretch_ratio overrides envelope_type preset."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(
            10.0, "helium",
            burst_stretch_ratio=4.0,
            envelope_type="latex",
        )
        expected = round(base * 4.0 * SAFE_FILL_PRESETS["latex"]["safe_fill_fraction"], 6)
        assert abs(safe - expected) < 0.0001

    def test_envelope_type_uses_preset_ratio(self):
        """Without explicit ratio, envelope_type uses its preset ratio."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(
            10.0, "helium", envelope_type="blimp"
        )
        blimp_preset = SAFE_FILL_PRESETS["blimp"]
        expected = round(base * blimp_preset["burst_stretch_ratio"] * blimp_preset["safe_fill_fraction"], 6)
        assert abs(safe - expected) < 0.0001

    def test_no_envelope_type_falls_back_to_default(self):
        """With no envelope_type and no explicit ratio, use DEFAULT_BURST_STRETCH_RATIO."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(10.0, "helium")
        expected = round(base * DEFAULT_BURST_STRETCH_RATIO * SAFETY_MARGIN, 6)
        assert abs(safe - expected) < 0.0001


# ─── Edge cases for missing parameters ───────────────────────────

class TestMissingParameters:
    """Edge cases when parameters are missing or unusual."""

    def test_all_optional_params_none(self):
        """All None -> defaults (ratio=2.5, fraction=0.6)."""
        safe = calculate_max_safe_gas_mass(
            10.0, "helium",
            burst_stretch_ratio=None,
            envelope_type=None,
            launch_pressure=None,
            launch_altitude=None,
            gas_temperature=None,
            safe_fill_data=None,
        )
        base = calculate_optimal_fill(10.0, "helium")
        expected = round(base * DEFAULT_BURST_STRETCH_RATIO * SAFETY_MARGIN, 6)
        assert abs(safe - expected) < 0.0001

    def test_unknown_envelope_type_falls_back_to_default(self):
        """Unknown envelope_type -> default ratio + SAFETY_MARGIN."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(10.0, "helium", envelope_type="unknown")
        expected = round(base * DEFAULT_BURST_STRETCH_RATIO * SAFETY_MARGIN, 6)
        assert abs(safe - expected) < 0.0001

    def test_empty_safe_fill_data(self):
        """Empty safe_fill_data -> uses defaults (no keys to override)."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(
            10.0, "helium", safe_fill_data={}
        )
        expected = round(base * DEFAULT_BURST_STRETCH_RATIO * SAFETY_MARGIN, 6)
        assert abs(safe - expected) < 0.0001

    def test_empty_safe_fill_data_with_envelope_type(self):
        """Empty safe_fill_data with envelope_type -> uses envelope preset."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(
            10.0, "helium",
            safe_fill_data={},
            envelope_type="latex",
        )
        latex_preset = SAFE_FILL_PRESETS["latex"]
        expected = round(base * latex_preset["burst_stretch_ratio"] * latex_preset["safe_fill_fraction"], 6)
        assert abs(safe - expected) < 0.0001

    def test_unknown_gas_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown gas"):
            calculate_max_safe_gas_mass(10.0, "xenon")


# ─── Various burst stretch ratios ────────────────────────────────

class TestBurstStretchRatios:
    """Test how different burst_stretch_ratio values affect safe mass."""

    def test_low_ratio_reduces_safe_mass(self):
        base = calculate_optimal_fill(10.0, "helium")
        safe_1_2 = calculate_max_safe_gas_mass(10.0, "helium", burst_stretch_ratio=1.2)
        safe_3_0 = calculate_max_safe_gas_mass(10.0, "helium", burst_stretch_ratio=3.0)
        assert safe_1_2 < safe_3_0

    def test_ratio_1_0_equals_fraction_of_base(self):
        """ratio=1.0 -> safe = base * 1.0 * 0.6 = base * 0.6."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(10.0, "helium", burst_stretch_ratio=1.0)
        expected = round(base * 0.6, 6)
        assert abs(safe - expected) < 0.0001

    def test_ratio_below_one_gives_tiny_safe_mass(self):
        """ratio=0.5 -> safe = base * 0.5 * 0.6 = base * 0.3."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(10.0, "helium", burst_stretch_ratio=0.5)
        expected = round(base * 0.5 * SAFETY_MARGIN, 6)
        assert abs(safe - expected) < 0.0001

    def test_high_ratio_raises_safe_mass(self):
        """ratio=5.0 -> safe = base * 5.0 * 0.6 = base * 3.0."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(10.0, "helium", burst_stretch_ratio=5.0)
        expected = round(base * 5.0 * SAFETY_MARGIN, 6)
        assert abs(safe - expected) < 0.0001

    def test_monotonic_increase_with_ratio(self):
        """Safe mass increases monotonically with burst_stretch_ratio."""
        prev = 0
        for ratio in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]:
            safe = calculate_max_safe_gas_mass(10.0, "helium", burst_stretch_ratio=ratio)
            assert safe > prev, f"Safe mass should increase at ratio={ratio}"
            prev = safe


# ─── Safe_fill_data override combinations ────────────────────────

class TestSafeFillDataOverrides:
    """Test safe_fill_data override behavior with various combinations."""

    def test_safe_fill_data_overrides_envelope_preset(self):
        """safe_fill_data takes precedence over envelope_type preset."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(
            10.0, "helium",
            envelope_type="blimp",
            safe_fill_data={
                "burst_stretch_ratio": 4.0,
                "safe_fill_fraction": 0.7,
            },
        )
        expected = round(base * 4.0 * 0.7, 6)
        assert abs(safe - expected) < 0.0001

    def test_safe_fill_data_with_explicit_ratio(self):
        """Both safe_fill_data and explicit burst_stretch_ratio -> data wins."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(
            10.0, "helium",
            burst_stretch_ratio=2.0,
            safe_fill_data={"burst_stretch_ratio": 3.0},
        )
        expected = round(base * 3.0 * SAFETY_MARGIN, 6)
        assert abs(safe - expected) < 0.0001

    def test_safe_fill_data_without_ratio_uses_explicit(self):
        """safe_fill_data with fraction only -> ratio from explicit arg."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(
            10.0, "helium",
            burst_stretch_ratio=2.0,
            safe_fill_data={"safe_fill_fraction": 0.5},
        )
        expected = round(base * 2.0 * 0.5, 6)
        assert abs(safe - expected) < 0.0001

    def test_safe_fill_data_without_ratio_uses_preset(self):
        """safe_fill_data with fraction only -> ratio from envelope preset."""
        base = calculate_optimal_fill(10.0, "helium")
        safe = calculate_max_safe_gas_mass(
            10.0, "helium",
            envelope_type="mylar",
            safe_fill_data={"safe_fill_fraction": 0.5},
        )
        mylar_ratio = SAFE_FILL_PRESETS["mylar"]["burst_stretch_ratio"]
        expected = round(base * mylar_ratio * 0.5, 6)
        assert abs(safe - expected) < 0.0001


# ─── Cross-validation ────────────────────────────────────────────

class TestCrossValidation:
    """Cross-validate safe mass calculations across all gases and envelopes."""

    def test_safe_mass_for_all_gases_and_envelopes(self):
        """Every gas × envelope combination produces a valid safe mass."""
        for gas in VALID_GAS_TYPES:
            for env_id, volume in ENVELOPE_VOLUMES.items():
                safe = calculate_max_safe_gas_mass(volume, gas, envelope_type=env_id)
                base = calculate_optimal_fill(volume, gas)
                assert safe > 0, f"Safe mass for {gas}/{env_id} should be positive"
                # Safe mass should be base * ratio * fraction
                preset = SAFE_FILL_PRESETS[env_id]
                expected = round(base * preset["burst_stretch_ratio"] * preset["safe_fill_fraction"], 6)
                assert abs(safe - expected) < 0.0001, f"Mismatch for {gas}/{env_id}"

    def test_safe_mass_increases_with_volume(self):
        """Safe mass should scale with volume for a given envelope type."""
        base_10 = calculate_max_safe_gas_mass(10.0, "helium", envelope_type="latex")
        base_100 = calculate_max_safe_gas_mass(100.0, "helium", envelope_type="latex")
        assert base_100 > base_10
        assert abs(base_100 / base_10 - 10.0) < 0.01
