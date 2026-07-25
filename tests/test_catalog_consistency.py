"""Balloon Frontier — Cross-module catalog consistency tests.

These tests enforce that the canonical CATALOG (the source of truth) and the
progression subsystem agree on every shared attribute.  If progression drifts
away the CI will catch it.
"""
import sys
sys.path.insert(0, "/tmp/BalloonFrontier")

import pytest
from balloon_frontier.catalog import CATALOG, PayloadDefinition, EnvelopeDefinition, GasDefinition, SiteDefinition
from balloon_frontier.progression import (
    PAYLOAD_UNLOCKS, ENVELOPES, SITES,
    PayloadUnlock, EnvelopeUnlock, SiteUnlock,
)


# ═══════════════════════════════════════════════════════════════════════════
# Payloads
# ═══════════════════════════════════════════════════════════════════════════

def _catalog_payload_map():
    return {p.id: p for p in CATALOG.all_payloads() if p.id != "none"}


def _progression_payload_map():
    return {p.id: p for p in PAYLOAD_UNLOCKS if p.id != "none"}


class TestPayloadIDs:
    """Every payload ID in progression must exist in catalog and vice versa."""

    def test_ids_match(self):
        cat_ids = set(_catalog_payload_map().keys())
        prog_ids = set(_progression_payload_map().keys())
        assert cat_ids == prog_ids, (
            f"Payload ID mismatch\n"
            f"  missing from catalog:  {prog_ids - cat_ids}\n"
            f"  missing from prog:     {cat_ids - prog_ids}"
        )

    def test_no_none_in_progression(self):
        """'none' is a UI sentinel, not an unlockable payload."""
        ids = {p.id for p in PAYLOAD_UNLOCKS}
        assert "none" not in ids, "'none' must not appear in PAYLOAD_UNLOCKS"


class TestPayloadNames:
    def test_names_match(self):
        cat_map = _catalog_payload_map()
        prog_map = _progression_payload_map()
        diffs = {}
        for pid in cat_map:
            if pid in prog_map and cat_map[pid].name != prog_map[pid].name:
                diffs[pid] = (cat_map[pid].name, prog_map[pid].name)
        assert not diffs, (
            f"Payload name mismatch:\n"
            + "\n".join(f"  {k}: catalog={v[0]!r} prog={v[1]!r}" for k, v in diffs.items())
        )


class TestPayloadMasses:
    def test_masses_match(self):
        cat_map = _catalog_payload_map()
        prog_map = _progression_payload_map()
        diffs = {}
        for pid in cat_map:
            if pid in prog_map:
                cat_m = cat_map[pid].mass_kg
                prog_m = prog_map[pid].mass_kg
                if abs(cat_m - prog_m) > 0.001:
                    diffs[pid] = (cat_m, prog_m)
        assert not diffs, (
            f"Payload mass mismatch:\n"
            + "\n".join(f"  {k}: catalog={v[0]} prog={v[1]}" for k, v in diffs.items())
        )


class TestPayloadHasValve:
    def test_has_valve_consistent_with_tag(self):
        """Payloads with has_valve=True must have a 'vent' tag in progression."""
        cat_map = _catalog_payload_map()
        prog_map = _progression_payload_map()
        for pid in cat_map:
            if pid in prog_map:
                cat_v = cat_map[pid].has_valve
                prog_has_vent = "vent" in prog_map[pid].tag
                assert cat_v == prog_has_vent, (
                    f"{pid}: catalog.has_valve={cat_v} but prog.tag={prog_map[pid].tag!r}"
                )


# ═══════════════════════════════════════════════════════════════════════════
# Envelopes
# ═══════════════════════════════════════════════════════════════════════════

def _catalog_envelope_map():
    return {e.id: e for e in CATALOG.all_envelopes()}


def _progression_envelope_map():
    return {e.id: e for e in ENVELOPES}


class TestEnvelopeIDs:
    def test_ids_match(self):
        cat_ids = set(_catalog_envelope_map().keys())
        prog_ids = set(_progression_envelope_map().keys())
        assert cat_ids == prog_ids, (
            f"Envelope ID mismatch\n"
            f"  missing from catalog:  {prog_ids - cat_ids}\n"
            f"  missing from prog:     {cat_ids - prog_ids}"
        )


class TestEnvelopeNames:
    def test_names_match(self):
        cat_map = _catalog_envelope_map()
        prog_map = _progression_envelope_map()
        diffs = {}
        for eid in cat_map:
            if eid in prog_map and cat_map[eid].name != prog_map[eid].name:
                diffs[eid] = (cat_map[eid].name, prog_map[eid].name)
        assert not diffs, (
            f"Envelope name mismatch:\n"
            + "\n".join(f"  {k}: catalog={v[0]!r} prog={v[1]!r}" for k, v in diffs.items())
        )


class TestEnvelopeMasses:
    def test_masses_match(self):
        cat_map = _catalog_envelope_map()
        prog_map = _progression_envelope_map()
        diffs = {}
        for eid in cat_map:
            if eid in prog_map:
                cat_m = cat_map[eid].mass_kg
                prog_m = prog_map[eid].mass_kg
                if abs(cat_m - prog_m) > 0.001:
                    diffs[eid] = (cat_m, prog_m)
        assert not diffs, (
            f"Envelope mass mismatch:\n"
            + "\n".join(f"  {k}: catalog={v[0]} prog={v[1]}" for k, v in diffs.items())
        )


class TestEnvelopeVolumes:
    def test_max_volume_matches(self):
        cat_map = _catalog_envelope_map()
        prog_map = _progression_envelope_map()
        diffs = {}
        for eid in cat_map:
            if eid in prog_map:
                cat_v = cat_map[eid].max_volume_m3
                prog_v = prog_map[eid].max_volume_m3
                if abs(cat_v - prog_v) > 0.01:
                    diffs[eid] = (cat_v, prog_v)
        assert not diffs, (
            f"Envelope volume mismatch:\n"
            + "\n".join(f"  {k}: catalog={v[0]} prog={v[1]}" for k, v in diffs.items())
        )


class TestEnvelopeStretch:
    def test_burst_stretch_ratio_matches(self):
        cat_map = _catalog_envelope_map()
        prog_map = _progression_envelope_map()
        diffs = {}
        for eid in cat_map:
            if eid in prog_map:
                cat_s = cat_map[eid].burst_stretch_ratio
                prog_s = prog_map[eid].burst_stretch_ratio
                if abs(cat_s - prog_s) > 0.01:
                    diffs[eid] = (cat_s, prog_s)
        assert not diffs, (
            f"Envelope burst_stretch_ratio mismatch:\n"
            + "\n".join(f"  {k}: catalog={v[0]} prog={v[1]}" for k, v in diffs.items())
        )


class TestEnvelopeContainedGas:
    def test_contained_gas_matches(self):
        cat_map = _catalog_envelope_map()
        prog_map = _progression_envelope_map()
        for eid in cat_map:
            if eid in prog_map:
                assert cat_map[eid].contained_gas == prog_map[eid].contained_gas, (
                    f"{eid}: catalog={cat_map[eid].contained_gas} prog={prog_map[eid].contained_gas}"
                )


# ═══════════════════════════════════════════════════════════════════════════
# Sites
# ═══════════════════════════════════════════════════════════════════════════

def _catalog_site_map():
    return {s.id: s for s in CATALOG.all_sites()}


def _progression_site_map():
    return {s.id: s for s in SITES}


class TestSiteIDs:
    def test_ids_match(self):
        cat_ids = set(_catalog_site_map().keys())
        prog_ids = set(_progression_site_map().keys())
        assert cat_ids == prog_ids, (
            f"Site ID mismatch\n"
            f"  missing from catalog:  {prog_ids - cat_ids}\n"
            f"  missing from prog:     {cat_ids - prog_ids}"
        )


class TestSiteNames:
    def test_names_match(self):
        cat_map = _catalog_site_map()
        prog_map = _progression_site_map()
        diffs = {}
        for sid in cat_map:
            if sid in prog_map and cat_map[sid].name != prog_map[sid].name:
                diffs[sid] = (cat_map[sid].name, prog_map[sid].name)
        assert not diffs, (
            f"Site name mismatch:\n"
            + "\n".join(f"  {k}: catalog={v[0]!r} prog={v[1]!r}" for k, v in diffs.items())
        )


# ═══════════════════════════════════════════════════════════════════════════
# Gas — catalog is the sole source; progression doesn't define gases.
# ═══════════════════════════════════════════════════════════════════════════

class TestGasIDs:
    def test_expected_gases_exist(self):
        ids = {g.id for g in CATALOG.all_gases()}
        expected = {"helium", "hydrogen", "hot_air", "methane"}
        assert ids == expected, f"Expected {expected}, got {ids}"


# ═══════════════════════════════════════════════════════════════════════════
# Discord UI consistency
# ═══════════════════════════════════════════════════════════════════════════

class TestDiscordUIPayloadIDs:
    """Discord PAYLOAD_OPTIONS must be a subset of catalog payload IDs.

    Not every catalog payload is exposed in Discord — extras are intentionally
    hidden until simulation behaviour is implemented.  This test ensures no
    Discord payload exists outside the catalog (prevents drift).
    """

    def test_discord_payload_ids_are_subset_of_catalog(self):
        from balloon_frontier.discord_ui.configurator import PAYLOAD_OPTIONS
        catalog_ids = {p.id for p in CATALOG.all_payloads() if p.id != "none"}
        ui_ids = {k for k in PAYLOAD_OPTIONS.keys() if k != "none"}
        assert ui_ids.issubset(catalog_ids), (
            f"Discord UI references payloads not in catalog:\n"
            f"  UI-only:       {ui_ids - catalog_ids}\n"
            f"  (catalog must be the authoritative source)"
        )


class TestDiscordUIEnvelopeIDs:
    def test_discord_envelope_ids_match_catalog(self):
        from balloon_frontier.discord_ui.configurator import ENVELOPE_OPTIONS
        catalog_ids = {e.id for e in CATALOG.all_envelopes()}
        ui_ids = set(ENVELOPE_OPTIONS.keys())
        assert catalog_ids == ui_ids, (
            f"Discord envelope IDs mismatch\n"
            f"  catalog-only:    {catalog_ids - ui_ids}\n"
            f"  UI-only:         {ui_ids - catalog_ids}"
        )


class TestDiscordUositeIDs:
    def test_discord_site_ids_match_catalog(self):
        from balloon_frontier.discord_ui.configurator import SITE_OPTIONS
        catalog_ids = {s.id for s in CATALOG.all_sites()}
        ui_ids = set(SITE_OPTIONS.keys())
        assert catalog_ids == ui_ids, (
            f"Discord site IDs mismatch\n"
            f"  catalog-only:    {catalog_ids - ui_ids}\n"
            f"  UI-only:         {ui_ids - catalog_ids}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Extras should NOT be in Discord UI
# ═══════════════════════════════════════════════════════════════════════════

class TestExtrasNotInDiscordUI:
    """Payloads that are in catalog/progression but not yet in Discord UI."""

    EXTRA_NOT_IN_UI = {
        "barometer", "gps_receiver", "parafoil",
        "propeller_pod", "solar_panel", "thermometer",
    }

    def test_extras_not_in_discord_payload_options(self):
        from balloon_frontier.discord_ui.configurator import PAYLOAD_OPTIONS
        ui_ids = set(PAYLOAD_OPTIONS.keys()) - {"none"}
        found = ui_ids & self.EXTRA_NOT_IN_UI
        assert not found, (
            f"Extras unexpectedly exposed in Discord UI: {found}\n"
            f"These payloads lack simulation behaviour — hide until implemented."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])