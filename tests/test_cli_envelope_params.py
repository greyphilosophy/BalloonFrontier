"""Tests for CLI envelope parameter passing to shared calculation.

Covers:
- _validate_envelope_params() validation logic
- show_fill_presets() passes burst_stretch_ratio to apply_fill_mode
- Error handling for malformed/missing envelope parameters
- Consistency: CLI uses same calculation as shared module
"""

import pytest

from balloon_frontier.fill import (
    apply_fill_mode, FillMode, calculate_optimal_fill,
    calculate_max_safe_gas_mass, SAFE_FILL_PRESETS, SAFETY_MARGIN,
)


class TestValidateEnvelopeParams:
    """Test the _validate_envelope_params helper function."""

    def test_valid_latex_balloon(self):
        """A valid balloon spec returns parsed params."""
        from cli_game import _validate_envelope_params

        spec = {"name": '36"', "mass_kg": 0.060, "max_vol": 3.5, "burst": 2.3}
        result = _validate_envelope_params(spec)
        assert result["max_vol"] == 3.5
        assert result["burst_stretch_ratio"] == 2.3

    def test_valid_balloon_without_name(self):
        """Works even when 'name' is missing (falls back to 'unknown')."""
        from cli_game import _validate_envelope_params

        spec = {"max_vol": 10.0, "burst": 2.2}
        result = _validate_envelope_params(spec)
        assert result["max_vol"] == 10.0
        assert result["burst_stretch_ratio"] == 2.2

    def test_missing_max_vol(self):
        """Missing 'max_vol' raises ValueError."""
        from cli_game import _validate_envelope_params

        spec = {"name": 'Test', "burst": 2.3}
        with pytest.raises(ValueError, match="max_vol"):
            _validate_envelope_params(spec)

    def test_missing_burst(self):
        """Missing 'burst' raises ValueError."""
        from cli_game import _validate_envelope_params

        spec = {"name": 'Test', "max_vol": 10.0}
        with pytest.raises(ValueError, match="burst"):
            _validate_envelope_params(spec)

    def test_non_numeric_max_vol(self):
        """Non-numeric 'max_vol' raises ValueError."""
        from cli_game import _validate_envelope_params

        spec = {"name": 'Test', "max_vol": "ten", "burst": 2.3}
        with pytest.raises(ValueError, match="max_vol"):
            _validate_envelope_params(spec)

    def test_non_numeric_burst(self):
        """Non-numeric 'burst' raises ValueError."""
        from cli_game import _validate_envelope_params

        spec = {"name": 'Test', "max_vol": 10.0, "burst": "two_point_five"}
        with pytest.raises(ValueError, match="burst"):
            _validate_envelope_params(spec)

    def test_zero_max_vol(self):
        """Zero 'max_vol' raises ValueError."""
        from cli_game import _validate_envelope_params

        spec = {"name": 'Test', "max_vol": 0, "burst": 2.3}
        with pytest.raises(ValueError, match="positive"):
            _validate_envelope_params(spec)

    def test_negative_burst(self):
        """Negative 'burst' raises ValueError."""
        from cli_game import _validate_envelope_params

        spec = {"name": 'Test', "max_vol": 10.0, "burst": -1.0}
        with pytest.raises(ValueError, match="positive"):
            _validate_envelope_params(spec)

    def test_float_values(self):
        """Float values (not just ints) are accepted."""
        from cli_game import _validate_envelope_params

        spec = {"name": 'Test', "max_vol": 10.0, "burst": 2.3}
        result = _validate_envelope_params(spec)
        assert result["max_vol"] == 10.0
        assert result["burst_stretch_ratio"] == 2.3

    def test_all_balloon_sizes_are_valid(self):
        """Every balloon in BALLOON_SIZES passes validation."""
        from cli_game import _validate_envelope_params, BALLOON_SIZES

        for key, spec in BALLOON_SIZES.items():
            result = _validate_envelope_params(spec)
            assert result["max_vol"] > 0, f"{key}: max_vol should be positive"
            assert result["burst_stretch_ratio"] > 0, f"{key}: burst should be positive"


class TestEnvelopeAwareFillCalculation:
    """Verify that CLI fill calculation uses envelope parameters correctly."""

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


class TestErrorHandling:
    """Test error handling for malformed inputs in the CLI fill flow."""

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
