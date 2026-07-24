"""Tests for the central game catalog (catalog.py).

These tests verify the typed dataclass definitions and the lookup API.
No behavioral changes — just schema verification.
"""

import pytest

from balloon_frontier.catalog import (
    CATALOG,
    GasDefinition,
    EnvelopeDefinition,
    BalloonDefinition,
    PayloadDefinition,
    SiteDefinition,
    FillMode,
    GAS_OPTIONS,
    PAYLOADS,
    DISCORD_GAS_OPTIONS,
    DISCORD_ENVELOPE_OPTIONS,
    DISCORD_PAYLOAD_OPTIONS,
)


# ─── GasDefinition tests ───────────────────────────────────────────


class TestGasDefinition:

    def test_all_gases_exist(self):
        gases = CATALOG.all_gases()
        assert len(gases) == 4

    def test_helium(self):
        g = CATALOG.gas("helium")
        assert g.id == "helium"
        assert g.name == "Helium"
        assert g.molar_mass == 0.0040026
        assert g.cost_per_kg == 5
        assert g.gas_behavior == "lighter"

    def test_hydrogen(self):
        g = CATALOG.gas("hydrogen")
        assert g.molar_mass == 0.002016
        assert g.cost_per_kg == 3

    def test_hot_air(self):
        g = CATALOG.gas("hot_air")
        assert g.molar_mass == 0.028965
        assert g.gas_behavior == "neutral"
        assert g.cost_per_kg == 1

    def test_methane(self):
        g = CATALOG.gas("methane")
        assert g.molar_mass == 0.01604
        assert g.cost_per_kg == 4

    def test_name_lookup_case_insensitive(self):
        assert CATALOG.gas("helium") is CATALOG.gas("Helium")
        assert CATALOG.gas("Helium") is CATALOG.gas("HELIUM")

    def test_unknown_gas_raises(self):
        with pytest.raises(KeyError, match="Unknown gas:"):
            CATALOG.gas("plasma")

    def test_gas_ids(self):
        ids = CATALOG.gas_ids()
        assert set(ids) == {"helium", "hydrogen", "hot_air", "methane"}

    def test_density_string(self):
        assert CATALOG.gas("helium").density_string == "ρ=0.0040026 kg/m³"

    def test_gases_by_behavior(self):
        lighter = CATALOG.gases_by_behavior("lighter")
        assert len(lighter) == 3
        assert all(g.gas_behavior == "lighter" for g in lighter)


# ─── EnvelopeDefinition tests ──────────────────────────────────────


class TestEnvelopeDefinition:

    def test_all_envelopes_exist(self):
        envs = CATALOG.all_envelopes()
        assert len(envs) == 4

    def test_latex(self):
        e = CATALOG.envelope("latex")
        assert e.id == "latex"
        assert e.name == "Latex Weather Balloon"
        assert e.max_volume_m3 == 10.0
        assert e.mass_kg == 1.0
        assert e.drag_coefficient == 3.0
        assert e.burst_stretch_ratio == 2.5
        assert e.contained_gas is True
        assert e.cost == 2000
        assert e.safe_fill_fraction == 0.6

    def test_mylar(self):
        e = CATALOG.envelope("mylar")
        assert e.max_volume_m3 == 200.0
        assert e.burst_stretch_ratio == 3.0
        assert e.safe_fill_fraction == 0.55

    def test_zero_pressure(self):
        e = CATALOG.envelope("zero_pressure")
        assert e.max_volume_m3 == 300.0
        assert e.burst_stretch_ratio == 1.8
        assert e.safe_fill_fraction == 0.65

    def test_blimp(self):
        e = CATALOG.envelope("blimp")
        assert e.max_volume_m3 == 500.0
        assert e.cost == 50000
        assert e.contained_gas is False

    def test_burst_volume_calculation(self):
        e = CATALOG.envelope("latex")
        assert e.burst_volume_m3 == 25.0  # 10.0 * 2.5

    def test_name_lookup_case_insensitive(self):
        assert CATALOG.envelope("latex") is CATALOG.envelope("Latex Weather Balloon")

    def test_unknown_envelope_raises(self):
        with pytest.raises(KeyError, match="Unknown envelope:"):
            CATALOG.envelope("toy")


# ─── BalloonDefinition tests ──────────────────────────────────────


class TestBalloonDefinition:

    def test_all_balloons_exist(self):
        balloons = CATALOG.all_balloons()
        assert len(balloons) == 8

    def test_s36(self):
        b = CATALOG.balloon("s36")
        assert b.name == "36\""
        assert b.mass_kg == 0.060
        assert b.max_volume_m3 == 3.5
        assert b.burst_stretch_ratio == 2.3
        assert b.fill_range_g == (30, 1158)

    def test_s45(self):
        b = CATALOG.balloon("s45")
        assert b.fill_range_g == (50, 1163)

    def test_s21_tiny(self):
        b = CATALOG.balloon("s21")
        assert b.max_volume_m3 == 0.6
        assert b.fill_range_g == (10, 120)

    def test_burst_volume(self):
        b = CATALOG.balloon("s36")
        assert b.burst_volume_m3 == 3.5 * 2.3  # 8.05

    def test_unknown_balloon_raises(self):
        with pytest.raises(KeyError, match="Unknown balloon size:"):
            CATALOG.balloon("s999")

    def test_balloon_ids(self):
        ids = CATALOG.balloon_ids()
        assert len(ids) == 8


# ─── PayloadDefinition tests ──────────────────────────────────────


class TestPayloadDefinition:

    def test_all_payloads_exist(self):
        payloads = CATALOG.all_payloads()
        assert len(payloads) == 9  # 8 real + pressure valve

    def test_camera(self):
        p = CATALOG.payload("camera")
        assert p.name == "Camera"
        assert p.mass_kg == 1.5
        assert p.cost == 500
        assert p.has_valve is False

    def test_battery(self):
        p = CATALOG.payload("battery")
        assert p.mass_kg == 3.0
        assert p.cost == 1000

    def test_valve(self):
        p = CATALOG.payload("valve")
        assert p.has_valve is True
        assert p.mass_kg == 0.3
        assert p.cost == 250

    def test_ballast_heaviest(self):
        p = CATALOG.payload("ballast")
        assert p.mass_kg == 15.0
        assert p.cost == 300

    def test_unknown_payload_raises(self):
        with pytest.raises(KeyError, match="Unknown payload:"):
            CATALOG.payload("tardis")

    def test_payload_ids(self):
        ids = CATALOG.payload_ids()
        assert "none" not in ids  # "none" is a sentinel, not a registered payload


# ─── SiteDefinition tests ─────────────────────────────────────────


class TestSiteDefinition:

    def test_all_sites_exist(self):
        sites = CATALOG.all_sites()
        assert len(sites) == 3

    def test_field(self):
        s = CATALOG.site("field")
        assert s.name == "Open Field"
        assert s.altitude_m == 0.0
        assert s.gas_temperature_k == 288.15
        assert s.wind_strength == 2.0

    def test_mountain(self):
        s = CATALOG.site("mountain")
        assert s.altitude_m == 1500.0
        assert s.gas_temperature_k == 278.15
        assert s.temperature_offset_k == -5.0
        assert s.wind_strength == 4.0

    def test_rooftop(self):
        s = CATALOG.site("rooftop")
        assert s.altitude_m == 50.0
        assert s.gas_temperature_k == 291.15
        assert s.temperature_offset_k == 3.0

    def test_unknown_site_raises(self):
        with pytest.raises(KeyError, match="Unknown site:"):
            CATALOG.site("moon_base")


# ─── FillMode tests ──────────────────────────────────────────────


class TestFillMode:

    def test_auto_multiplier(self):
        assert FillMode.AUTO.get_multiplier() == 1.0

    def test_light_multiplier(self):
        assert FillMode.LIGHT.get_multiplier() == 0.8

    def test_normal_multiplier(self):
        assert FillMode.NORMAL.get_multiplier() == 1.0

    def test_heavy_multiplier(self):
        assert FillMode.HEAVY.get_multiplier() == 1.2

    def test_manual_raises(self):
        with pytest.raises(ValueError, match="MANUAL mode requires"):
            FillMode.MANUAL.get_multiplier()

    def test_labels(self):
        assert FillMode.AUTO.label == "Auto (Optimal)"
        assert FillMode.LIGHT.label == "Light"
        assert FillMode.MANUAL.label == "Manual"

    def test_descriptions(self):
        assert "optimal" in FillMode.AUTO.description.lower()
        assert "burst" in FillMode.LIGHT.description.lower()

    def test_enum_values(self):
        assert FillMode.AUTO.value == "auto"
        assert FillMode.MANUAL.value == "manual"


# ─── Backward-compatibility shims ─────────────────────────────────


class TestBackwardCompatShims:

    def test_gas_options_shim(self):
        """cli_game.py style: {"id": (name, molar_mass, behavior)}"""
        g = GAS_OPTIONS["helium"]
        assert isinstance(g, tuple)
        assert len(g) == 3
        assert g[0] == "Helium"
        assert g[1] == 0.0040026
        assert g[2] == "lighter"

    def test_discord_gas_shim(self):
        """discord_bot.py style: {"id": (name, molar_mass, cost)}"""
        g = DISCORD_GAS_OPTIONS["helium"]
        assert g == ("Helium", 0.0040026, 5)

    def test_discord_envelope_shim(self):
        """discord_bot.py style: {"id": (name, vol, mass, drag, burst, cost)}"""
        e = DISCORD_ENVELOPE_OPTIONS["latex"]
        assert e == ("Latex Weather Balloon", 10.0, 1.0, 3.0, 2.5, 2000)
        m = DISCORD_ENVELOPE_OPTIONS["mylar"]
        assert m == ("Mylar Party Balloon", 200.0, 0.05, 2.0, 3.0, 500)

    def test_discord_payload_shim(self):
        """discord_bot.py style: {"id": (name, mass, cost, has_valve)}"""
        p = DISCORD_PAYLOAD_OPTIONS["camera"]
        assert p == ("Camera", 1.5, 500, False)
        v = DISCORD_PAYLOAD_OPTIONS["valve"]
        assert v == ("Pressure Valve", 0.3, 250, True)
        n = DISCORD_PAYLOAD_OPTIONS["none"]
        assert n == ("None", 1.0, 100, False)

    def test_catalog_sources_shims(self):
        """Shims derive from catalog, so they reflect catalog changes."""
        # Gas count should match
        assert len(GAS_OPTIONS) == len(CATALOG.gas_ids())
        assert len(DISCORD_GAS_OPTIONS) == len(CATALOG.gas_ids())
        assert len(DISCORD_ENVELOPE_OPTIONS) == len(CATALOG.envelope_ids())
        assert len(DISCORD_PAYLOAD_OPTIONS) == len(CATALOG.payload_ids()) + 1  # +1 for "none"

    def test_gases_match_cli_and_discord(self):
        """Same gas definitions in both shims."""
        for gas_id in CATALOG.gas_ids():
            cli = GAS_OPTIONS[gas_id]
            disc = DISCORD_GAS_OPTIONS[gas_id]
            assert cli[0] == disc[0]  # name
            assert cli[1] == disc[1]  # molar_mass