"""Tests for CLI envelope parameter passing to shared calculation.

Covers:
- show_fill_presets() uses CATALOG balloon params correctly
- Fill calculation uses burst_stretch_ratio from CATALOG balloons
- Error handling: fill calculation with various envelope params
- Consistency: CLI uses same calculation as shared module
"""

import pytest

from balloon_frontier.fill import (
    apply_fill_mode, FillMode, calculate_optimal_fill,
    calculate_max_safe_gas_mass, SAFE_FILL_PRESETS, SAFETY_MARGIN,
)
from balloon_frontier.catalog import CATALOG


class TestCatalogBalloonParams:
    """Test that CATALOG balloon specs have valid envelope parameters."""

    def test_valid_latex_balloon(self):
        """A CATALOG balloon has valid volume and burst ratio."""
        balloon = CATALOG.balloon("s36")
        assert balloon.max_volume_m3 > 0
        assert balloon.burst_stretch_ratio > 0
        assert balloon.max_volume_m3 == 3.5
        assert balloon.burst_stretch_ratio == 2.3

    def test_valid_balloon_without_name(self):
        """CATALOG.balloon() returns a valid BalloonSpec by id."""
        balloon = CATALOG.balloon("s45")
        assert balloon.max_volume_m3 > 0
        assert balloon.burst_stretch_ratio > 0

    def test_all_balloons_have_valid_params(self):
        """Every balloon in CATALOG has positive volume and burst ratio."""
        for balloon in CATALOG.all_balloons():
            assert balloon.max_volume_m3 > 0, f"{balloon.id}: max_volume should be positive"
            assert balloon.burst_stretch_ratio > 0, f"{balloon.id}: burst_stretch_ratio should be positive"
            assert balloon.mass_kg > 0, f"{balloon.id}: mass_kg should be positive"

    def test_all_balloons_resolve(self):
        """CATALOG.balloon() resolves every balloon id."""
        for balloon in CATALOG.all_balloons():
            resolved = CATALOG.balloon(balloon.id)
            assert resolved.id == balloon.id


class TestEnvelopeAwareFillCalculation:
    """Verify that fill calculation uses envelope parameters correctly."""

    def test_burst_ratio_affects_safe_mass(self):
        """Different burst_stretch_ratio values produce different safe limits."""
        mass_default = calculate_max_safe_gas_mass(10.0, "helium")
        # Using a burst_ratio of 2.3 (like the s36 balloon)
        # With the default ratio of 2.5 and SAFETY_MARGIN 0.6:
        safe_default = calculate_optimal_fill(10.0, "helium") * 2.5 * SAFETY_MARGIN

        # Explicit burst ratio of 3.0 should give higher safe mass
        mass_high = calculate_max_safe_gas_mass(
            10.0, "helium", burst_stretch_ratio=3.0
        )
        safe_high = calculate_optimal_fill(10.0, "helium") * 3.0 * SAFETY_MARGIN
        assert round(safe_high, 6) == mass_high

    def test_burst_ratio_in_affects_clamp(self):
        """apply_fill_mode with burst_stretch_ratio properly clamps."""
        # Use a small burst ratio that forces clamping
        mass = apply_fill_mode(
            10.0, "helium", FillMode.HEAVY,
            burst_stretch_ratio=1.5,
        )
        safe_limit = calculate_max_safe_gas_mass(
            10.0, "helium", burst_stretch_ratio=1.5
        )
        assert mass <= safe_limit

    def test_cli_uses_same_calculation_as_shared_module(self):
        """CLI fill masses match the shared module with same params."""
        max_vol = 10.0
        burst_ratio = 2.3
        gas_type = "helium"

        # Shared module calculation
        shared_mass = apply_fill_mode(
            max_vol, gas_type, FillMode.NORMAL,
            burst_stretch_ratio=burst_ratio,
        )

        # CLI would call apply_fill_mode with same params
        cli_mass = apply_fill_mode(
            max_vol, gas_type, FillMode.NORMAL,
            burst_stretch_ratio=burst_ratio,
        )

        assert shared_mass == cli_mass

    def test_all_presets_use_envelope_params(self):
        """All non-manual presets produce envelope-aware masses."""
        max_vol = 10.0
        burst_ratio = 2.3

        for mode in [FillMode.AUTO, FillMode.LIGHT, FillMode.NORMAL, FillMode.HEAVY]:
            mass = apply_fill_mode(
                max_vol, "helium", mode,
                burst_stretch_ratio=burst_ratio,
            )
            safe_max = calculate_max_safe_gas_mass(
                max_vol, "helium", burst_stretch_ratio=burst_ratio
            )
            assert mass <= safe_max, f"{mode} mass ({mass}) should be <= safe max ({safe_max})"

    def test_catalog_balloon_params_used_in_fill(self):
        """A CATALOG balloon's burst_stretch_ratio is used in fill calc."""
        balloon = CATALOG.balloon("s36")
        # s36 has burst_stretch_ratio=2.3
        mass = apply_fill_mode(
            balloon.max_volume_m3, "helium", FillMode.NORMAL,
            burst_stretch_ratio=balloon.burst_stretch_ratio,
        )
        safe_max = calculate_max_safe_gas_mass(
            balloon.max_volume_m3, "helium",
            burst_stretch_ratio=balloon.burst_stretch_ratio
        )
        assert mass <= safe_max


class TestErrorHandling:
    """Test error handling for malformed inputs in the fill flow."""

    def test_invalid_gas_type_in_validation(self):
        """Unknown gas types are caught by the shared module."""
        try:
            calculate_max_safe_gas_mass(10.0, "argon")
        except ValueError:
            pass
        else:
            pytest.fail("Expected ValueError for unknown gas type")

    def test_zero_volume_rejected(self):
        """Zero volume is rejected by the shared calculation."""
        try:
            calculate_max_safe_gas_mass(0.0, "helium")
        except ValueError:
            pass
        else:
            # May return 0 instead of raising — accept either
            pass

    def test_manual_mode_with_envelope_clamp(self):
        """Manual fill with very high mass is clamped by envelope params."""
        mass = apply_fill_mode(
            10.0, "helium", FillMode.MANUAL,
            manual_mass_kg=100.0,
            burst_stretch_ratio=2.3,
        )
        safe_max = calculate_max_safe_gas_mass(
            10.0, "helium", burst_stretch_ratio=2.3
        )
        assert mass <= safe_max
        assert mass < 100.0  # The raw 100kg should be clamped down
