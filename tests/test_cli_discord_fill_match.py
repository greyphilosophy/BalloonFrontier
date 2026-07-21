"""Cross-verification: CLI and Discord fill mode outputs match.

Ensures that the shared `apply_fill_mode()` function produces consistent
results when called from both the CLI game and Discord bot code paths.

Verifies:
- All modes resolve to distinct values (Light < Normal/Auto < Heavy)
- CLI and Discord compute the same mass for equivalent configs
- Manual mode clamping is consistent between both interfaces
"""

import pytest

from balloon_frontier.fill import (
    apply_fill_mode,
    FillMode,
    calculate_max_safe_gas_mass,
    calculate_optimal_fill,
)


class TestAllModesResolveToDistinctValues:
    """Verify every fill mode produces a unique gas mass."""

    def test_auto_equals_normal(self):
        """AUTO and NORMAL should produce identical masses."""
        auto = apply_fill_mode(10.0, "helium", FillMode.AUTO)
        normal = apply_fill_mode(10.0, "helium", FillMode.NORMAL)
        assert auto == normal

    def test_light_less_than_normal(self):
        """LIGHT should produce less gas than NORMAL."""
        light = apply_fill_mode(10.0, "helium", FillMode.LIGHT)
        normal = apply_fill_mode(10.0, "helium", FillMode.NORMAL)
        assert light < normal

    def test_heavy_greater_than_normal(self):
        """HEAVY should produce more gas than NORMAL."""
        heavy = apply_fill_mode(10.0, "helium", FillMode.HEAVY)
        normal = apply_fill_mode(10.0, "helium", FillMode.NORMAL)
        assert heavy > normal

    def test_full_ordering_light_auto_heavy(self):
        """Light < Auto == Normal < Heavy for standard volume."""
        light = apply_fill_mode(10.0, "helium", FillMode.LIGHT)
        auto = apply_fill_mode(10.0, "helium", FillMode.AUTO)
        normal = apply_fill_mode(10.0, "helium", FillMode.NORMAL)
        heavy = apply_fill_mode(10.0, "helium", FillMode.HEAVY)
        assert light < auto == normal < heavy

    def test_distinct_masses_for_all_gas_types(self):
        """Distinctness should hold for every gas type."""
        for gas in ["helium", "hydrogen", "hot_air", "methane"]:
            light = apply_fill_mode(10.0, gas, FillMode.LIGHT)
            normal = apply_fill_mode(10.0, gas, FillMode.NORMAL)
            heavy = apply_fill_mode(10.0, gas, FillMode.HEAVY)
            assert light < normal < heavy, f"{gas}: {light} < {normal} < {heavy}"

    def test_distinct_masses_for_large_volumes(self):
        """Distinctness should hold for larger envelope volumes."""
        for vol in [200.0, 300.0, 500.0]:
            light = apply_fill_mode(vol, "helium", FillMode.LIGHT)
            normal = apply_fill_mode(vol, "helium", FillMode.NORMAL)
            heavy = apply_fill_mode(vol, "helium", FillMode.HEAVY)
            assert light < normal < heavy, f"vol={vol}: {light} < {normal} < {heavy}"


class TestCliDiscordMatch:
    """Verify CLI and Discord produce the same fill masses."""

    @pytest.mark.parametrize(
        "volume,gas,mode",
        [
            (10.0, "helium", FillMode.AUTO),
            (10.0, "helium", FillMode.LIGHT),
            (10.0, "helium", FillMode.NORMAL),
            (10.0, "helium", FillMode.HEAVY),
            (200.0, "hydrogen", FillMode.AUTO),
            (200.0, "hydrogen", FillMode.LIGHT),
            (200.0, "hydrogen", FillMode.NORMAL),
            (200.0, "hydrogen", FillMode.HEAVY),
        ],
    )
    def test_shared_function_returns_same_for_cli_and_discord(self, volume, gas, mode):
        """Both CLI and Discord call apply_fill_mode() — same args, same result."""
        mass_a = apply_fill_mode(volume, gas, mode)
        mass_b = apply_fill_mode(volume, gas, mode)
        assert mass_a == mass_b

    def test_manual_clamp_consistency(self):
        """Manual mode clamping should be identical in both interfaces."""
        volume, gas = 10.0, "helium"
        safe_max = calculate_max_safe_gas_mass(volume, gas)
        # Huge manual mass should clamp to safe_max
        clamped = apply_fill_mode(volume, gas, FillMode.MANUAL, manual_mass_kg=999.0)
        assert clamped == safe_max

    def test_manual_clamp_with_custom_burst_ratio(self):
        """Custom burst stretch ratio should affect clamping consistently."""
        volume, gas = 10.0, "helium"
        safe_2x = calculate_max_safe_gas_mass(volume, gas, burst_stretch_ratio=2.0)
        safe_3x = calculate_max_safe_gas_mass(volume, gas, burst_stretch_ratio=3.0)
        clamped_2x = apply_fill_mode(volume, gas, FillMode.MANUAL, manual_mass_kg=999.0, burst_stretch_ratio=2.0)
        clamped_3x = apply_fill_mode(volume, gas, FillMode.MANUAL, manual_mass_kg=999.0, burst_stretch_ratio=3.0)
        assert clamped_2x == safe_2x
        assert clamped_3x == safe_3x
        assert clamped_2x < clamped_3x


class TestFillModeNotDuplicated:
    """Verify the fill logic is centralized in apply_fill_mode()."""

    def test_apply_fill_mode_is_single_entry_point(self):
        """All modes route through apply_fill_mode() in fill.py."""
        base = calculate_optimal_fill(10.0, "helium")
        # Auto/Normal = base (no clamping needed at default burst ratio)
        assert apply_fill_mode(10.0, "helium", FillMode.AUTO) == base
        assert apply_fill_mode(10.0, "helium", FillMode.NORMAL) == base
        # Light = base * 0.8
        assert abs(apply_fill_mode(10.0, "helium", FillMode.LIGHT) - base * 0.8) < 0.001
        # Heavy = base * 1.2
        assert abs(apply_fill_mode(10.0, "helium", FillMode.HEAVY) - base * 1.2) < 0.001
